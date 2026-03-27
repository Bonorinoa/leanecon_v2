"""Statement-shaping utilities for LeanEcon v2."""

from __future__ import annotations

from typing import Any, Literal

from src.models import FormalizeResponse

RAW_LEAN_MARKERS = ("theorem ", "lemma ", "example ", ":= by", "by\n")
NEEDS_DEFINITION_MARKERS = ("custom axiom", "define a new", "new notion", "introduce")


def scope_check(raw_claim: str) -> Literal["IN_SCOPE", "NEEDS_DEFINITIONS", "RAW_LEAN"]:
    """Classify a claim before formalization."""

    lowered = raw_claim.lower()
    if any(marker in lowered for marker in RAW_LEAN_MARKERS):
        return "RAW_LEAN"
    if any(marker in lowered for marker in NEEDS_DEFINITION_MARKERS):
        return "NEEDS_DEFINITIONS"
    return "IN_SCOPE"


async def formalize_claim(raw_claim: str, search_context: dict[str, Any]) -> FormalizeResponse:
    """Phase 2A placeholder for theorem-stub generation."""

    return FormalizeResponse(
        success=False,
        theorem_code=None,
        scope=scope_check(raw_claim),
        search_context=search_context,
        attempts=0,
        errors=["Formalization is coming in Phase 3."],
        message="Coming in Phase 3",
    )
