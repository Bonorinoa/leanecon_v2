"""Formalizer tests for the Phase 3 implementation."""

from __future__ import annotations

import pytest

from src.formalizer import formalize_claim, scope_check
from src.formalizer import formalizer as formalizer_module


def test_scope_check_identifies_raw_lean() -> None:
    """Raw Lean snippets should bypass the natural-language path."""

    assert scope_check("theorem x : True := by\n  sorry") == "RAW_LEAN"


@pytest.mark.anyio
async def test_formalize_claim_generates_budget_set_stub() -> None:
    """Formalization should generate a compile-valid theorem stub."""

    response = await formalize_claim(
        (
            "A two-good bundle with spending p1 * x1 + p2 * x2 less than or equal "
            "to income m lies in the budget set."
        ),
        preamble_names=["budget_set"],
    )

    assert response.success is True
    assert response.theorem_code is not None
    assert "in_budget_set" in response.theorem_code
    assert "sorry" in response.theorem_code


@pytest.mark.anyio
async def test_formalize_claim_accepts_raw_lean_stub() -> None:
    """Raw Lean theorem stubs should be accepted when they compile with sorry."""

    response = await formalize_claim("theorem raw_budget : 1 + 1 = 2 := by\n  sorry\n")

    assert response.success is True
    assert response.scope == "RAW_LEAN"


@pytest.mark.anyio
async def test_formalize_claim_falls_back_when_provider_errors(monkeypatch) -> None:
    """Provider failures should fall back to the deterministic theorem template."""

    class FailingDriver:
        @property
        def name(self) -> str:
            return "mistral"

        async def formalize(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            max_tokens: int = 4096,
        ) -> str:
            _ = system_prompt
            _ = user_prompt
            _ = max_tokens
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(formalizer_module, "_provider_driver", lambda: FailingDriver())

    response = await formalize_claim(
        (
            "An eligible two-good bundle with spending p1 * x1 + p2 * x2 less than or equal "
            "to income m belongs to the budget set."
        ),
        preamble_names=["budget_set"],
    )

    assert response.success is True
    assert response.theorem_code is not None
    assert "in_budget_set" in response.theorem_code
