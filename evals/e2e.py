"""In-process end-to-end evaluation runner."""

from __future__ import annotations

import argparse
import asyncio

from evals.common import load_claims, make_client, poll_job


async def _run(claim_set: str) -> int:
    claims = load_claims(claim_set)
    successes = 0

    async with make_client() as client:
        for claim in claims:
            search_response = await client.post(
                "/api/v2/search",
                json={"raw_claim": claim["raw_claim"]},
            )
            search_response.raise_for_status()

            formalize_response = await client.post(
                "/api/v2/formalize",
                json={
                    "raw_claim": claim["raw_claim"],
                    "preamble_names": claim.get("preamble_names"),
                },
            )
            formalize_response.raise_for_status()
            formalize_payload = formalize_response.json()

            verify_input = (
                claim.get("theorem_stub")
                or claim.get("raw_lean")
                or formalize_payload.get("theorem_code")
            )
            if not verify_input:
                continue

            verify_response = await client.post(
                "/api/v2/verify",
                json={"theorem_with_sorry": verify_input},
            )
            verify_response.raise_for_status()
            verify_payload = verify_response.json()
            terminal = await poll_job(client, verify_payload["job_id"])
            if terminal["status"] == "completed":
                successes += 1

    print(f"{claim_set}: verified {successes}/{len(claims)} jobs")
    return 0 if successes == len(claims) else 1


def main() -> int:
    """Run an in-process eval loop against the local FastAPI app."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-set", default="tier0_smoke")
    args = parser.parse_args()
    return asyncio.run(_run(args.claim_set))


if __name__ == "__main__":
    raise SystemExit(main())
