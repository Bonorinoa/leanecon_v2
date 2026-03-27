"""In-process formalizer-only evaluation runner."""

from __future__ import annotations

import argparse
import asyncio

from evals.common import load_claims, make_client


async def _run(claim_set: str) -> int:
    claims = load_claims(claim_set)
    successes = 0

    async with make_client() as client:
        for claim in claims:
            response = await client.post(
                "/api/v2/formalize",
                json={
                    "raw_claim": claim["raw_claim"],
                    "preamble_names": claim.get("preamble_names"),
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("success"):
                successes += 1

    print(f"{claim_set}: formalized {successes}/{len(claims)} claims")
    return 0 if successes == len(claims) else 1


def main() -> int:
    """Run the formalizer-only eval loop."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-set", default="tier0_smoke")
    args = parser.parse_args()
    return asyncio.run(_run(args.claim_set))


if __name__ == "__main__":
    raise SystemExit(main())
