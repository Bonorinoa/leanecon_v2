"""Search engine tests for the Phase 2A scaffold."""

from __future__ import annotations

from src.search.engine import search_claim


def test_search_claim_handles_empty_workspace_gracefully() -> None:
    """Search should still return a stable response when no Lean files exist."""

    response = search_claim("Consumers maximize utility.")

    assert response.domain == "economics"
    assert response.preamble_matches == []
    assert "LeanEcon.Preamble.Optimization" in response.candidate_imports
