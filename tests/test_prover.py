"""Verification harness tests for the Phase 3 implementation."""

from __future__ import annotations

import pytest

from src.drivers.base import DriverConfig
from src.drivers.registry import get_prover_driver
from src.prover import VerificationHarness
from src.prover.file_controller import ProofFileController
from src.prover.tool_tracker import BudgetTracker


@pytest.mark.anyio
async def test_verification_harness_solves_simple_arithmetic(tmp_path) -> None:
    """The local fast path should discharge easy arithmetic goals."""

    harness = VerificationHarness(
        driver=get_prover_driver("mistral", DriverConfig(model="mistral-small", api_key=None)),
        file_controller=ProofFileController(workspace_root=tmp_path),
        budget_tracker=BudgetTracker(),
    )
    result = await harness.verify(
        "import Mathlib\n\ntheorem benchmark_one_plus_one : 1 + 1 = 2 := by\n  sorry\n",
        "job_arith",
    )

    assert result.status == "completed"
    assert result.result is not None
    assert result.result["status"] == "verified"


@pytest.mark.anyio
async def test_verification_harness_uses_budget_set_fast_path(tmp_path) -> None:
    """Budget-set membership stubs should be closed by the local simpa tactic."""

    harness = VerificationHarness(
        driver=get_prover_driver("mistral", DriverConfig(model="mistral-small", api_key=None)),
        file_controller=ProofFileController(workspace_root=tmp_path),
        budget_tracker=BudgetTracker(),
    )
    theorem = (
        "import Mathlib\nimport LeanEcon.Preamble.Consumer.BudgetSet\n\n"
        "theorem benchmark_budget_set_membership\n"
        "    (p1 p2 m x1 x2 : ℝ)\n"
        "    (hbudget : p1 * x1 + p2 * x2 ≤ m) :\n"
        "    in_budget_set p1 p2 m x1 x2 := by\n"
        "  sorry\n"
    )
    result = await harness.verify(theorem, "job_budget")

    assert result.status == "completed"
    assert result.result is not None
    assert result.result["status"] == "verified"
