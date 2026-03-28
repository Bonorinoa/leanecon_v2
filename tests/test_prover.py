"""Verification harness tests for the Phase 3 implementation."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from src.drivers.base import DriverConfig, DriverEvent, ToolCall, ToolResult
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


class FakeRewriteDriver:
    """Small fake driver that exercises the provider tool loop."""

    @property
    def name(self) -> str:
        return "fake"

    async def prove(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools,
        on_tool_call: Callable[[ToolCall], ToolResult],
        max_steps: int = 64,
    ):
        _ = tools
        _ = max_steps
        assert "compile_current_code" in system_prompt
        assert "provider_tool_rewrite" in user_prompt
        tool_call = ToolCall(
            id="call_1",
            name="write_current_code",
            arguments={
                "theorem_code": (
                    "import Mathlib\n\n"
                    "theorem provider_tool_rewrite : True := by\n"
                    "  trivial\n"
                )
            },
        )
        yield DriverEvent(type="tool_call", data={"name": tool_call.name})
        result = on_tool_call(tool_call)
        yield DriverEvent(type="tool_result", data={"content": result.content})
        yield DriverEvent(type="done", data={"content": "done"})


@pytest.mark.anyio
async def test_verification_harness_provider_loop_writes_checkpoints(tmp_path, monkeypatch) -> None:
    """Provider edits should flow through the harness and create checkpoints."""

    monkeypatch.setattr("src.prover.harness.suggest_fast_path_tactics", lambda _code: [])

    harness = VerificationHarness(
        driver=FakeRewriteDriver(),
        file_controller=ProofFileController(workspace_root=tmp_path),
        budget_tracker=BudgetTracker(),
    )
    result = await harness.verify(
        "import Mathlib\n\ntheorem provider_tool_rewrite : True := by\n  sorry\n",
        "job_provider",
        max_steps=4,
    )

    assert result.status == "completed"
    assert result.result is not None
    assert result.result["tool_history"] == ["write_current_code"]
    assert (tmp_path / "checkpoints" / "job_provider_1001.lean").exists()


@pytest.mark.anyio
async def test_verification_harness_fails_cleanly_without_provider_key(
    tmp_path,
    monkeypatch,
) -> None:
    """When fast paths fail and no provider is configured, the harness should fail cleanly."""

    monkeypatch.setattr("src.prover.harness.suggest_fast_path_tactics", lambda _code: [])

    harness = VerificationHarness(
        driver=get_prover_driver("mistral", DriverConfig(model="mistral-small", api_key=None)),
        file_controller=ProofFileController(workspace_root=tmp_path),
        budget_tracker=BudgetTracker(),
    )
    result = await harness.verify(
        "import Mathlib\n\ntheorem provider_missing_key (P : Prop) : P := by\n  sorry\n",
        "job_missing_key",
        max_steps=4,
    )

    assert result.status == "failed"
    assert result.error == "MISTRAL_API_KEY is not configured."


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
