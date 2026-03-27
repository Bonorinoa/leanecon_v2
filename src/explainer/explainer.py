"""Natural-language explanation helpers for verification results."""

from __future__ import annotations

from typing import Any


def explain_verification_result(verification_result: dict[str, Any]) -> str:
    """Produce a compact explanation from a structured verification result."""

    status = verification_result.get("status", "unknown")
    theorem = verification_result.get("theorem", "theorem")

    if status == "verified":
        return f"The kernel accepted {theorem}, so the claim is formally certified."
    if status == "failed":
        return f"The verification run for {theorem} failed; inspect diagnostics for the blocker."
    return f"The verification status for {theorem} is {status}."
