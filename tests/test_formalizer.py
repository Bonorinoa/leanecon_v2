"""Formalizer tests for the Phase 3 implementation."""

from __future__ import annotations

import pytest

from src.formalizer import formalize_claim, scope_check
from src.formalizer import formalizer as formalizer_module


def test_scope_check_identifies_raw_lean() -> None:
    """Raw Lean snippets should bypass the natural-language path."""

    assert scope_check("theorem x : True := by\n  sorry") == "RAW_LEAN"


def test_vacuous_prop_claim_rejected() -> None:
    """A `(claim : Prop) : claim` theorem must not pass as meaningful."""

    vacuous, reason = formalizer_module.is_vacuous_formalization(
        "theorem demo\n    (claim : Prop) :\n    claim := by\n  sorry"
    )

    assert vacuous
    assert "vacuous" in reason.lower()


def test_vacuous_identity_rejected() -> None:
    """An identity-function theorem should be treated as vacuous."""

    vacuous, _ = formalizer_module.is_vacuous_formalization(
        "theorem demo (h : P) : P := h"
    )

    assert vacuous


def test_real_theorem_not_vacuous() -> None:
    """A genuine economics theorem should not be flagged as vacuous."""

    vacuous, _ = formalizer_module.is_vacuous_formalization(
        "import Mathlib\nimport LeanEcon.Preamble.Consumer.CRRAUtility\n\n"
        "theorem crra_rra (c γ : ℝ) (hc : 0 < c) (hg : γ ≠ 1) : "
        "rra (crra_utility c γ) = γ := by\n  sorry"
    )

    assert not vacuous


def test_faithfulness_catches_missing_demand() -> None:
    """Dropping demand content from a demand claim should be flagged."""

    result = formalizer_module.check_semantic_faithfulness(
        "Marshallian demand for good 1 equals alpha * m / p1",
        "theorem demo (x : ℝ) : x = x := by sorry",
    )

    assert not result["faithful"]
    assert "demand" in result["missing_concepts"] or "marshallian" in result["missing_concepts"]


def test_faithfulness_passes_real_formalization() -> None:
    """A faithful CRRA formalization should satisfy the heuristic check."""

    result = formalizer_module.check_semantic_faithfulness(
        "Under CRRA utility, relative risk aversion equals gamma",
        "theorem crra_rra_constant (c γ : ℝ) (hc : 0 < c) : "
        "rra (crra_utility c γ) = γ := by sorry",
    )

    assert result["faithful"]


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


@pytest.mark.anyio
async def test_formalize_claim_uses_discount_factor_heuristic_when_provider_errors(
    monkeypatch,
) -> None:
    """Known core preambles should still produce faithful stubs on provider failure."""

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
            "With geometric discounting, the present value of a constant stream x for T "
            "periods is x * (1 - beta^T) / (1 - beta)."
        ),
        preamble_names=["discount_factor"],
    )

    assert response.success is True
    assert response.theorem_code is not None
    assert "present_value_constant" in response.theorem_code


@pytest.mark.anyio
async def test_formalize_claim_rejects_vacuous_provider_output(monkeypatch) -> None:
    """Compile-valid vacuous output should be rejected after generation."""

    class VacuousDriver:
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
            return "theorem demo (claim : Prop) : claim := by\n  sorry\n"

    monkeypatch.setattr(formalizer_module, "_provider_driver", lambda: VacuousDriver())

    response = await formalize_claim(
        "A contraction mapping on a complete metric space has a unique fixed point."
    )

    assert response.success is False
    assert response.scope == "VACUOUS"
    assert response.theorem_code is not None
    assert "(claim : Prop)" in response.theorem_code


@pytest.mark.anyio
async def test_formalize_claim_prefers_faithful_heuristic_over_vacuous_provider(
    monkeypatch,
) -> None:
    """Known faithful heuristics should rescue vacuous provider output without another LLM call."""

    class VacuousDriver:
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
            return "theorem demo (claim : Prop) : claim := by\n  sorry\n"

    monkeypatch.setattr(formalizer_module, "_provider_driver", lambda: VacuousDriver())

    response = await formalize_claim(
        (
            "With geometric discounting, the present value of a constant stream x for T "
            "periods is x * (1 - beta^T) / (1 - beta)."
        ),
        preamble_names=["discount_factor"],
    )

    assert response.success is True
    assert response.scope == "IN_SCOPE"
    assert response.theorem_code is not None
    assert "present_value_constant" in response.theorem_code
    assert "(claim : Prop)" not in response.theorem_code


@pytest.mark.anyio
async def test_formalize_claim_preserves_formalization_failed(monkeypatch) -> None:
    """Explicit provider refusals should surface as honest formalization failures."""

    class HonestFailDriver:
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
            return "FORMALIZATION_FAILED: missing faithful LeanEcon identifier for this claim"

    monkeypatch.setattr(formalizer_module, "_provider_driver", lambda: HonestFailDriver())

    response = await formalize_claim("A brand-new custom economic operator has a fixed point.")

    assert response.success is False
    assert response.theorem_code is None
    assert "missing faithful leanecon identifier" in response.errors[0].lower()
