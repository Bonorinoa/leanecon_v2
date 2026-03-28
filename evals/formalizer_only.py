"""In-process formalizer-only evaluation runner."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from time import perf_counter

from evals.common import (
    frequency_table,
    load_claims,
    make_client,
    summarize_counts,
    summarize_latencies,
    write_summary,
)


async def _run(claim_set: str, *, output_path: Path | None = None) -> int:
    claims = load_claims(claim_set)
    successes = 0
    latencies: list[float] = []
    attempts_used: list[int] = []
    scopes: list[str] = []
    cases: list[dict[str, object]] = []

    async with make_client() as client:
        for claim in claims:
            started = perf_counter()
            response = await client.post(
                "/api/v2/formalize",
                json={
                    "raw_claim": claim["raw_claim"],
                    "preamble_names": claim.get("preamble_names"),
                },
            )
            response.raise_for_status()
            payload = response.json()
            latency = perf_counter() - started
            latencies.append(latency)
            attempts = int(payload.get("attempts", 0))
            attempts_used.append(attempts)
            scope = str(payload.get("scope", "UNKNOWN"))
            scopes.append(scope)
            success = bool(payload.get("success"))
            if success:
                successes += 1
            cases.append(
                {
                    "id": claim.get("id") or claim["raw_claim"][:80],
                    "success": success,
                    "scope": scope,
                    "attempts": attempts,
                    "latency_seconds": latency,
                }
            )

    summary = {
        "total_claims": len(claims),
        "successes": successes,
        "failures": len(claims) - successes,
        "pass_at_1": (successes / len(claims)) if claims else 0.0,
        "latency_seconds": summarize_latencies(latencies),
        "attempts": summarize_counts(attempts_used),
        "scope_distribution": frequency_table(scopes),
        "cases": cases,
    }
    artifact_path = write_summary(
        "formalizer_only",
        claim_set,
        summary,
        output_path=output_path,
    )
    print(
        f"{claim_set}: formalized {successes}/{len(claims)} claims | "
        f"pass@1={summary['pass_at_1']:.3f} | artifact={artifact_path}"
    )
    return 0 if successes == len(claims) else 1


def main() -> int:
    """Run the formalizer-only eval loop."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-set", default="tier0_smoke")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    return asyncio.run(_run(args.claim_set, output_path=args.output))


if __name__ == "__main__":
    raise SystemExit(main())
