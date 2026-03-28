"""Simple reporting entrypoint for LeanEcon eval claim sets."""

from __future__ import annotations

import json

from evals.common import default_output_path, load_claims


def main() -> int:
    """Print a compact count of claims per bundled eval set."""

    for claim_set in ("tier0_smoke", "tier1_core", "tier2_frontier"):
        claims = load_claims(claim_set)
        print(f"{claim_set}: {len(claims)} claims")
        for runner_name in ("formalizer_only", "prover_only", "e2e"):
            artifact_path = default_output_path(runner_name, claim_set)
            if not artifact_path.exists():
                continue
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            pass_at_1 = payload.get("pass_at_1")
            if isinstance(pass_at_1, (int, float)):
                print(f"  {runner_name}: pass@1={pass_at_1:.3f} ({artifact_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
