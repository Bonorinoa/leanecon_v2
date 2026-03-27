"""Simple reporting entrypoint for LeanEcon eval claim sets."""

from __future__ import annotations

from evals.common import load_claims


def main() -> int:
    """Print a compact count of claims per bundled eval set."""

    for claim_set in ("tier0_smoke", "tier1_core", "tier2_frontier"):
        claims = load_claims(claim_set)
        print(f"{claim_set}: {len(claims)} claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
