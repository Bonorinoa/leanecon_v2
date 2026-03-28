"""In-process prover-only evaluation runner."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from time import perf_counter

from evals.common import (
    frequency_table,
    load_claims,
    make_client,
    poll_job,
    summarize_counts,
    summarize_latencies,
    write_summary,
)


async def _run(claim_set: str, *, output_path: Path | None = None) -> int:
    claims = load_claims(claim_set)
    successes = 0
    attempted = 0
    skipped = 0
    latencies: list[float] = []
    attempt_counts: list[int] = []
    tool_count_samples: list[int] = []
    tool_names: list[str] = []
    terminal_statuses: list[str] = []
    cases: list[dict[str, object]] = []

    async with make_client() as client:
        for claim in claims:
            theorem_with_sorry = claim.get("theorem_stub") or claim.get("raw_lean")
            if not theorem_with_sorry:
                skipped += 1
                continue
            attempted += 1
            started = perf_counter()
            response = await client.post(
                "/api/v2/verify",
                json={"theorem_with_sorry": theorem_with_sorry},
            )
            response.raise_for_status()
            payload = response.json()
            terminal = await poll_job(client, payload["job_id"])
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
            cases.append(
                {
                    "id": claim.get("id") or theorem_with_sorry.splitlines()[0][:80],
                    "status": terminal["status"],
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
