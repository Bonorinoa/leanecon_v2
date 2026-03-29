"""In-process end-to-end evaluation runner."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from time import perf_counter

from evals.common import (
    claim_prefix,
    classify_job_error,
    extract_tool_budget,
    frequency_table,
    job_progress_line,
    job_progress_payload,
    job_result_payload,
    load_claims,
    log_line,
    make_client,
    poll_job,
    summarize_counts,
    summarize_latencies,
    summarize_tool_budget,
    write_summary,
)
from src.config import MAX_PROVE_TIMEOUT


async def _run(claim_set: str, *, output_path: Path | None = None) -> int:
    claims = load_claims(claim_set)
    total_claims = len(claims)
    successes = 0
    formalize_successes = 0
    verify_successes = 0
    latencies: list[float] = []
    formalize_attempts: list[int] = []
    terminal_statuses: list[str] = []
    tool_calls_made_samples: list[int] = []
    max_total_tool_calls_seen: list[int] = []
    max_search_tool_calls_seen: list[int] = []
    cases: list[dict[str, object]] = []

    log_line(f"[e2e] claim set '{claim_set}' with {total_claims} claims")
    async with make_client() as client:
        for claim_index, claim in enumerate(claims, start=1):
            prefix = claim_prefix("e2e", claim_index, total_claims, claim)
            verify_timeout = MAX_PROVE_TIMEOUT
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

            verify_input = formalize_payload.get("theorem_code")
            if not verify_input:
                latencies.append(perf_counter() - started)
                log_line(f"{prefix}: skipped (formalizer produced no verification input)")
                cases.append(
                    {
                        "id": claim.get("id") or claim["raw_claim"][:80],
                        "status": "skipped",
                        "latency_seconds": latencies[-1],
                        "formalize_success": bool(formalize_payload.get("success")),
                        "formalize_attempts": int(formalize_payload.get("attempts", 0)),
                        "tool_calls_made": 0,
                        "max_tool_calls": None,
                        "max_search_tool_calls": None,
                        "last_stage": None,
                        "error_message": "Formalizer produced no verification input.",
                        "error_type": "skipped",
                        "stop_reason": None,
                    }
                )
                continue

            log_line(f"{prefix}: submitting verification job")
            verify_response = await client.post(
                "/api/v2/verify",
                json={
                    "theorem_with_sorry": verify_input,
                    "timeout": verify_timeout,
                },
            )
            verify_response.raise_for_status()
            verify_payload = verify_response.json()
            job_id = verify_payload["job_id"]
            log_line(f"{prefix}: queued job {job_id}")
            last_stage: str | None = None

            def on_update(
                job_payload: dict[str, object],
                *,
                heartbeat: bool = False,
                _prefix: str = prefix,
            ) -> None:
                nonlocal last_stage
                progress = job_progress_payload(job_payload)
                stage = progress.get("stage")
                if stage is not None:
                    last_stage = str(stage)
                suffix = " (waiting)" if heartbeat else ""
                log_line(f"{_prefix}: {job_progress_line(job_payload)}{suffix}")

            terminal = await poll_job(
                client,
                job_id,
                timeout_seconds=verify_timeout + 15.0,
                on_update=on_update,
            )
            latency = perf_counter() - started
            latencies.append(latency)
            terminal_statuses.append(str(terminal["status"]))
            result = job_result_payload(terminal)
            tool_budget = extract_tool_budget(result)
            tool_calls_made = tool_budget["tool_calls_made"]
            if tool_calls_made is not None:
                tool_calls_made_samples.append(tool_calls_made)
            if tool_budget["max_total_tool_calls"] is not None:
                max_total_tool_calls_seen.append(tool_budget["max_total_tool_calls"])
            if tool_budget["max_search_tool_calls"] is not None:
                max_search_tool_calls_seen.append(tool_budget["max_search_tool_calls"])
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
                    "tool_calls_made": tool_calls_made,
                    "max_tool_calls": tool_budget["max_total_tool_calls"],
                    "max_search_tool_calls": tool_budget["max_search_tool_calls"],
                    "last_stage": last_stage,
                    "error_message": terminal.get("error"),
                    "error_type": classify_job_error(str(terminal["status"]), result),
                    "stop_reason": result.get("stop_reason"),
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
        "tool_budget": summarize_tool_budget(
            tool_calls_made_samples,
            max_total_tool_calls=(
                max(max_total_tool_calls_seen) if max_total_tool_calls_seen else None
            ),
            max_search_tool_calls=max(max_search_tool_calls_seen)
            if max_search_tool_calls_seen
            else None,
        ),
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
