"""In-process prover-only evaluation runner."""

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
    attempted = 0
    skipped = 0
    latencies: list[float] = []
    attempt_counts: list[int] = []
    tool_count_samples: list[int] = []
    tool_names: list[str] = []
    terminal_statuses: list[str] = []
    tool_calls_made_samples: list[int] = []
    max_total_tool_calls_seen: list[int] = []
    max_search_tool_calls_seen: list[int] = []
    cases: list[dict[str, object]] = []

    log_line(f"[prover_only] claim set '{claim_set}' with {total_claims} claims")
    async with make_client() as client:
        for claim_index, claim in enumerate(claims, start=1):
            prefix = claim_prefix("prover_only", claim_index, total_claims, claim)
            verify_timeout = MAX_PROVE_TIMEOUT
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
                json={
                    "theorem_with_sorry": theorem_with_sorry,
                    "timeout": verify_timeout,
                },
            )
            response.raise_for_status()
            payload = response.json()
            job_id = payload["job_id"]
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
            attempts = result.get("attempts") or []
            tool_history = [str(item) for item in result.get("tool_history") or []]
            tool_budget = extract_tool_budget(result)
            tool_calls_made = tool_budget["tool_calls_made"]
            if tool_calls_made is not None:
                tool_calls_made_samples.append(tool_calls_made)
            if tool_budget["max_total_tool_calls"] is not None:
                max_total_tool_calls_seen.append(tool_budget["max_total_tool_calls"])
            if tool_budget["max_search_tool_calls"] is not None:
                max_search_tool_calls_seen.append(tool_budget["max_search_tool_calls"])
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
                    "tool_calls_made": tool_calls_made,
                    "max_tool_calls": tool_budget["max_total_tool_calls"],
                    "max_search_tool_calls": tool_budget["max_search_tool_calls"],
                    "last_stage": last_stage,
                    "error_message": terminal.get("error"),
                    "error_type": classify_job_error(terminal_status, result),
                    "stop_reason": result.get("stop_reason"),
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
