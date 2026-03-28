"""In-process end-to-end evaluation runner."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from time import perf_counter

from evals.common import (
    claim_prefix,
    frequency_table,
    job_progress_line,
    load_claims,
    make_client,
    poll_job,
    log_line,
    summarize_counts,
    summarize_latencies,
    write_summary,
)


async def _run(claim_set: str, *, output_path: Path | None = None) -> int:
    claims = load_claims(claim_set)
    total_claims = len(claims)
    successes = 0
    formalize_successes = 0
    verify_successes = 0
    latencies: list[float] = []
    formalize_attempts: list[int] = []
    terminal_statuses: list[str] = []
    cases: list[dict[str, object]] = []

    log_line(f"[e2e] claim set '{claim_set}' with {total_claims} claims")
    async with make_client() as client:
        for claim_index, claim in enumerate(claims, start=1):
            prefix = claim_prefix("e2e", claim_index, total_claims, claim)
            log_line(f"{prefix}: search")
            started = perf_counter()
            search_response = await client.post(
                "/api/v2/search",
                json={"raw_claim": claim["raw_claim"]},
            )
            search_response.raise_for_status()
            log_line(f"{prefix}: search complete")

            log_line(f"{prefix}: formalize")
            formalize_response = await client.post(
                "/api/v2/formalize",
                json={
                    "raw_claim": claim["raw_claim"],
                    "preamble_names": claim.get("preamble_names"),
                },
            )
            formalize_response.raise_for_status()
            formalize_payload = formalize_response.json()
            if formalize_payload.get("success"):
                formalize_successes += 1
            formalize_attempts.append(int(formalize_payload.get("attempts", 0)))
            log_line(
                f"{prefix}: formalize complete | "
                f"success={bool(formalize_payload.get('success'))} | "
                f"attempts={int(formalize_payload.get('attempts', 0))}"
            )

            verify_input = (
                claim.get("theorem_stub")
                or claim.get("raw_lean")
                or formalize_payload.get("theorem_code")
            )
            if not verify_input:
                latencies.append(perf_counter() - started)
                log_line(f"{prefix}: skipped (no verification input)")
                cases.append(
                    {
                        "id": claim.get("id") or claim["raw_claim"][:80],
                        "status": "skipped",
                        "latency_seconds": latencies[-1],
                        "formalize_success": bool(formalize_payload.get("success")),
                    }
                )
                continue

            log_line(f"{prefix}: submitting verification job")
            verify_response = await client.post(
                "/api/v2/verify",
                json={"theorem_with_sorry": verify_input},
            )
            verify_response.raise_for_status()
            verify_payload = verify_response.json()
            job_id = verify_payload["job_id"]
            log_line(f"{prefix}: queued job {job_id}")

            def on_update(job_payload: dict[str, object], *, heartbeat: bool = False) -> None:
                suffix = " (waiting)" if heartbeat else ""
                log_line(f"{prefix}: {job_progress_line(job_payload)}{suffix}")

            terminal = await poll_job(client, job_id, on_update=on_update)
            latency = perf_counter() - started
            latencies.append(latency)
            terminal_statuses.append(str(terminal["status"]))
            if terminal["status"] == "completed":
                successes += 1
                verify_successes += 1
                log_line(f"{prefix}: verified in {latency:.1f}s")
            else:
                terminal_error = terminal.get("error") or "unknown error"
                log_line(
                    f"{prefix}: failed in {latency:.1f}s | "
                    f"error={terminal_error}"
                )
            cases.append(
                {
                    "id": claim.get("id") or claim["raw_claim"][:80],
                    "status": terminal["status"],
                    "latency_seconds": latency,
                    "formalize_success": bool(formalize_payload.get("success")),
                    "formalize_attempts": int(formalize_payload.get("attempts", 0)),
                }
            )

    summary = {
        "total_claims": len(claims),
        "formalize_successes": formalize_successes,
        "verify_successes": verify_successes,
        "end_to_end_successes": successes,
        "end_to_end_failures": len(claims) - successes,
        "pass_at_1": (successes / len(claims)) if claims else 0.0,
        "latency_seconds": summarize_latencies(latencies),
        "formalize_attempts": summarize_counts(formalize_attempts),
        "terminal_status_distribution": frequency_table(terminal_statuses),
        "cases": cases,
    }
    artifact_path = write_summary(
        "e2e",
        claim_set,
        summary,
        output_path=output_path,
    )
    print(
        f"{claim_set}: verified {successes}/{len(claims)} jobs | "
        f"pass@1={summary['pass_at_1']:.3f} | artifact={artifact_path}"
    )
    return 0 if successes == len(claims) else 1


def main() -> int:
    """Run an in-process eval loop against the local FastAPI app."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-set", default="tier0_smoke")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    return asyncio.run(_run(args.claim_set, output_path=args.output))


if __name__ == "__main__":
    raise SystemExit(main())
