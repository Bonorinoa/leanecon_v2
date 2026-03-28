"""In-process prover-only evaluation runner."""

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
    attempted = 0
    skipped = 0
    latencies: list[float] = []
    attempt_counts: list[int] = []
    tool_count_samples: list[int] = []
    tool_names: list[str] = []
    terminal_statuses: list[str] = []
    cases: list[dict[str, object]] = []

    log_line(f"[prover_only] claim set '{claim_set}' with {total_claims} claims")
    async with make_client() as client:
        for claim_index, claim in enumerate(claims, start=1):
            prefix = claim_prefix("prover_only", claim_index, total_claims, claim)
            theorem_with_sorry = claim.get("theorem_stub") or claim.get("raw_lean")
            if not theorem_with_sorry:
                skipped += 1
                log_line(f"{prefix}: skipped (missing theorem stub)")
                continue
            attempted += 1
            log_line(f"{prefix}: submitting verification job")
            started = perf_counter()
            response = await client.post(
                "/api/v2/verify",
                json={"theorem_with_sorry": theorem_with_sorry},
            )
            response.raise_for_status()
            payload = response.json()
            job_id = payload["job_id"]
            log_line(f"{prefix}: queued job {job_id}")

            def on_update(job_payload: dict[str, object], *, heartbeat: bool = False) -> None:
                suffix = " (waiting)" if heartbeat else ""
                log_line(f"{prefix}: {job_progress_line(job_payload)}{suffix}")

            terminal = await poll_job(client, job_id, on_update=on_update)
            latency = perf_counter() - started
            latencies.append(latency)
            terminal_statuses.append(str(terminal["status"]))
            result = terminal.get("result") or {}
            attempts = result.get("attempts") or []
            tool_history = [str(item) for item in result.get("tool_history") or []]
            attempt_counts.append(len(attempts))
            tool_count_samples.append(len(tool_history))
            tool_names.extend(tool_history)
            if terminal["status"] == "completed":
                successes += 1
            terminal_status = str(terminal["status"])
            if terminal_status == "completed":
                log_line(
                    f"{prefix}: completed in {latency:.1f}s | "
                    f"attempts={len(attempts)} | tool_calls={len(tool_history)}"
                )
            else:
                terminal_error = terminal.get("error") or "unknown error"
                log_line(
                    f"{prefix}: failed in {latency:.1f}s | "
                    f"error={terminal_error}"
                )
            cases.append(
                {
                    "id": claim.get("id") or theorem_with_sorry.splitlines()[0][:80],
                    "status": terminal_status,
                    "latency_seconds": latency,
                    "attempt_count": len(attempts),
                    "tool_calls": len(tool_history),
                }
            )

    summary = {
        "total_claims": len(claims),
        "attempted_claims": attempted,
        "skipped_claims": skipped,
        "successes": successes,
        "failures": max(attempted - successes, 0),
        "pass_at_1": (successes / attempted) if attempted else 0.0,
        "latency_seconds": summarize_latencies(latencies),
        "attempts": summarize_counts(attempt_counts),
        "tool_calls": summarize_counts(tool_count_samples),
        "tool_call_distribution": frequency_table(tool_names),
        "terminal_status_distribution": frequency_table(terminal_statuses),
        "cases": cases,
    }
    artifact_path = write_summary(
        "prover_only",
        claim_set,
        summary,
        output_path=output_path,
    )
    print(
        f"{claim_set}: proved {successes}/{attempted} theorem stubs | "
        f"pass@1={summary['pass_at_1']:.3f} | artifact={artifact_path}"
    )
    return 0 if successes == len(claims) else 1


def main() -> int:
    """Run the prover-only eval loop."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-set", default="tier0_smoke")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    return asyncio.run(_run(args.claim_set, output_path=args.output))


if __name__ == "__main__":
    raise SystemExit(main())
