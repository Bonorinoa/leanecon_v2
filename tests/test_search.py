"""Search engine tests for the Phase 3 implementation."""

from __future__ import annotations

from src.search.engine import build_formalization_context, search_claim


def test_search_claim_surfaces_real_preamble_matches() -> None:
    """Search should return actual preamble matches from the Lean workspace."""

    response = search_claim("CRRA utility has constant relative risk aversion.")

    assert response.domain == "economics"
    assert response.preamble_matches
    match_names = [match.name for match in response.preamble_matches]
    assert "crra_utility" in match_names
    assert "LeanEcon.Preamble.Consumer.CRRAUtility" in response.candidate_imports


def test_build_formalization_context_respects_explicit_preambles() -> None:
    """Explicit preamble selections should flow into the prompt context."""

    context = build_formalization_context(
        "A bundle satisfying the budget inequality belongs to the budget set.",
        explicit_preamble_names=["budget_set"],
    )

    assert context.explicit_preamble_names == ["budget_set"]
    assert "LeanEcon.Preamble.Consumer.BudgetSet" in context.preamble_imports
