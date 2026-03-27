"""In-process prover-only evaluation runner."""

from __future__ import annotations

import argparse
import asyncio

from evals.common import load_claims, make_client, poll_job


async def _run(claim_set: str) -> int:
    claims = load_claims(claim_set)
    successes = 0

    async with make_client() as client:
        for claim in claims:
            theorem_with_sorry = claim.get("theorem_stub") or claim.get("raw_lean")
            if not theorem_with_sorry:
                continue
            response = await client.post(
                "/api/v2/verify",
                json={"theorem_with_sorry": theorem_with_sorry},
            )
            response.raise_for_status()
            payload = response.json()
            terminal = await poll_job(client, payload["job_id"])
            if terminal["status"] == "completed":
                successes += 1

    print(f"{claim_set}: proved {successes}/{len(claims)} theorem stubs")
    return 0 if successes == len(claims) else 1


def main() -> int:
    """Run the prover-only eval loop."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-set", default="tier0_smoke")
    args = parser.parse_args()
    return asyncio.run(_run(args.claim_set))


if __name__ == "__main__":
    raise SystemExit(main())
