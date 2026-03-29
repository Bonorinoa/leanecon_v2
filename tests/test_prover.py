"""Verification harness tests for the Phase 3 implementation."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest

from lean_interact.interface import LeanError
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


class FakeLeanREPLSession:
    """Small fake REPL session for proving harness regression tests."""

    instances: int = 0
    start_calls: int = 0
    tactic_calls: list[str] = []
    verify_calls: list[str] = []

    def __init__(self, *args, **kwargs):
        _ = args
        _ = kwargs
        type(self).instances += 1
        self.call_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        _ = exc_type
        _ = exc
        _ = tb
        return False

    def start_proof(self, theorem_with_sorry: str, *, timeout=None):
        _ = timeout
        type(self).start_calls += 1
        self.theorem_with_sorry = theorem_with_sorry
        return SimpleNamespace(goal="⊢ goal")

    def apply_tactic(self, tactic: str, *, timeout=None):
        _ = timeout
        type(self).tactic_calls.append(tactic)
        self.call_count += 1
        self.tactic = tactic
        proof_status = "Incomplete: open goals remain" if self.call_count == 1 else "Completed"
        return SimpleNamespace(has_errors=lambda: False, proof_status=proof_status)

    def materialize_proof(self) -> str:
        return self.theorem_with_sorry.replace("sorry", self.tactic)

    def verify_materialized_proof(self, *, filename: str = "repl_verified.lean", timeout=None):
        _ = filename
        _ = timeout
        type(self).verify_calls.append(filename)
        return {
            "success": True,
            "errors": [],
            "warnings": [],
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }


@pytest.mark.anyio
async def test_verification_harness_uses_repl_fast_path(tmp_path, monkeypatch) -> None:
    """The fast path should prefer LeanInteract before subprocess compilation."""

    compile_calls: list[str | None] = []
    FakeLeanREPLSession.instances = 0
    FakeLeanREPLSession.start_calls = 0
    FakeLeanREPLSession.tactic_calls = []
    FakeLeanREPLSession.verify_calls = []

    def fake_compile_check(lean_code: str, *, timeout=None, filename=None, check_axioms=False):
        _ = lean_code
        _ = timeout
        _ = check_axioms
        compile_calls.append(filename)
        return {
            "success": False,
            "has_sorry": True,
            "axiom_warnings": [],
            "output": "",
            "errors": [],
            "warnings": [],
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr("src.prover.harness.compile_check", fake_compile_check)
    monkeypatch.setattr("src.prover.harness.suggest_fast_path_tactics", lambda _code: ["simp", "norm_num"])
    monkeypatch.setattr("src.prover.harness.LeanREPLSession", FakeLeanREPLSession)

    harness = VerificationHarness(
        driver=get_prover_driver("mistral", DriverConfig(model="mistral-small", api_key=None)),
        file_controller=ProofFileController(workspace_root=tmp_path),
        budget_tracker=BudgetTracker(),
    )
    result = await harness.verify(
        "import Mathlib\n\n" "theorem repl_fast_path_demo : 1 + 1 = 2 := by\n" "  sorry\n",
        "job_repl_fast_path",
    )

    assert result.status == "completed"
    assert result.result is not None
    assert result.result["attempts"][0]["mode"] == "repl_fast_path"
    assert result.result["attempts"][1]["mode"] == "repl_fast_path"
    assert result.result["attempts"][1]["proof_status"] == "Completed"
    assert FakeLeanREPLSession.instances == 1
    assert FakeLeanREPLSession.start_calls == 1
    assert FakeLeanREPLSession.tactic_calls == ["simp", "norm_num"]
    assert FakeLeanREPLSession.verify_calls == ["job_repl_fast_path_fast_2.lean"]
    assert compile_calls == ["job_repl_fast_path_initial.lean"]


class FailingLeanREPLSession:
    """Fake REPL session that never closes the theorem."""

    instances: int = 0
    start_calls: int = 0
    tactic_calls: list[str] = []

    def __init__(self, *args, **kwargs):
        _ = args
        _ = kwargs
        type(self).instances += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        _ = exc_type
        _ = exc
        _ = tb
        return False

    def start_proof(self, theorem_with_sorry: str, *, timeout=None):
        _ = timeout
        _ = theorem_with_sorry
        type(self).start_calls += 1
        return SimpleNamespace(goal="⊢ goal")

    def apply_tactic(self, tactic: str, *, timeout=None):
        _ = timeout
        type(self).tactic_calls.append(tactic)
        return LeanError(message=f"tactic failed: {tactic}")


@pytest.mark.anyio
async def test_verification_harness_falls_back_after_failed_repl_pass(tmp_path, monkeypatch) -> None:
    """A failed REPL pass should record the error and fall back once, not reopen sessions."""

    compile_calls: list[str | None] = []
    FailingLeanREPLSession.instances = 0
    FailingLeanREPLSession.start_calls = 0
    FailingLeanREPLSession.tactic_calls = []

    def fake_compile_check(lean_code: str, *, timeout=None, filename=None, check_axioms=False):
        _ = lean_code
        _ = timeout
        _ = check_axioms
        compile_calls.append(filename)
        success = filename == "job_repl_fallback_fast_1.lean"
        return {
            "success": success,
            "has_sorry": not success,
            "axiom_warnings": [],
            "output": "",
            "errors": [],
            "warnings": [],
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr("src.prover.harness.compile_check", fake_compile_check)
    monkeypatch.setattr("src.prover.harness.suggest_fast_path_tactics", lambda _code: ["norm_num"])
    monkeypatch.setattr("src.prover.harness.LeanREPLSession", FailingLeanREPLSession)

    harness = VerificationHarness(
        driver=get_prover_driver("mistral", DriverConfig(model="mistral-small", api_key=None)),
        file_controller=ProofFileController(workspace_root=tmp_path),
        budget_tracker=BudgetTracker(),
    )
    result = await harness.verify(
        "import Mathlib\n\n" "theorem repl_fallback_demo : 1 + 1 = 2 := by\n" "  sorry\n",
        "job_repl_fallback",
    )

    assert result.status == "completed"
    assert result.result is not None
    assert result.result["repl_fast_path"]["success"] is False
    assert result.result["repl_fast_path"]["attempts"][0]["success"] is False
    assert result.result["repl_fast_path"]["attempts"][0]["errors"] == ["tactic failed: norm_num"]
    assert FailingLeanREPLSession.instances == 1
    assert FailingLeanREPLSession.start_calls == 1
    assert FailingLeanREPLSession.tactic_calls == ["norm_num"]
    assert compile_calls == ["job_repl_fallback_initial.lean", "job_repl_fallback_fast_1.lean"]
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


class SlowDriver:
    """Fake driver that hangs forever, simulating a timeout scenario."""

    @property
    def name(self) -> str:
        return "slow_fake"

    async def prove(self, *, system_prompt, user_prompt, tools, on_tool_call, max_steps=64):
        import asyncio

        # Read current code (one tool call before stalling)
        read_call = ToolCall(id="call_slow_1", name="read_current_code", arguments={})
        yield DriverEvent(type="tool_call", data={"name": read_call.name})
        on_tool_call(read_call)
        yield DriverEvent(type="tool_result", data={"content": "read ok"})

        # Stall forever (simulates a slow LLM or long computation)
        await asyncio.sleep(3600)
        yield DriverEvent(type="done", data={"content": "should never reach here"})


class CompileSuccessDriver:
    """Fake driver that compiles successfully and then stalls forever."""

    @property
    def name(self) -> str:
        return "compile_success_fake"

    async def prove(self, *, system_prompt, user_prompt, tools, on_tool_call, max_steps=64):
        import asyncio

        _ = system_prompt
        _ = user_prompt
        _ = tools
        _ = max_steps

        write_call = ToolCall(
            id="call_compile_1",
            name="write_current_code",
            arguments={
                "theorem_code": (
                    "import Mathlib\n\n"
                    "theorem provider_compile_success : True := by\n"
                    "  trivial\n"
                )
            },
        )
        yield DriverEvent(type="tool_call", data={"name": write_call.name})
        write_result = on_tool_call(write_call)
        yield DriverEvent(
            type="tool_result",
            data={"name": write_call.name, "content": write_result.content},
        )

        compile_call = ToolCall(id="call_compile_2", name="compile_current_code", arguments={})
        yield DriverEvent(type="tool_call", data={"name": compile_call.name})
        compile_result = on_tool_call(compile_call)
        yield DriverEvent(
            type="tool_result",
            data={"name": compile_call.name, "content": compile_result.content},
        )

        await asyncio.sleep(3600)
        yield DriverEvent(type="done", data={"content": "should never reach here"})


@pytest.mark.anyio
async def test_timeout_returns_structured_partial_result(tmp_path, monkeypatch) -> None:
    """When verification times out, the result should include structured failure data."""
    import asyncio

    monkeypatch.setattr("src.prover.harness.suggest_fast_path_tactics", lambda _code: [])

    harness = VerificationHarness(
        driver=SlowDriver(),
        file_controller=ProofFileController(workspace_root=tmp_path),
        budget_tracker=BudgetTracker(),
    )

    last_stage = "init"

    def progress_tracker(stage, payload):
        nonlocal last_stage
        last_stage = stage

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(2):
            await harness.verify(
                "import Mathlib\n\ntheorem timeout_test : True := by\n  sorry\n",
                "job_timeout",
                on_progress=progress_tracker,
                max_steps=4,
            )

    # After timeout, the harness state should be accessible
    assert harness.budget_tracker.total_tool_calls == 1
    assert harness.budget_tracker.tool_history == ["read_current_code"]

    # Build partial result the same way the API does
    partial = {
        "partial": True,
        "stop_reason": "timeout",
        "tool_calls_made": harness.budget_tracker.total_tool_calls,
        "last_stage": last_stage,
        "tool_history": list(harness.budget_tracker.tool_history),
        "tool_budget": harness.budget_tracker.snapshot(),
    }
    assert partial["partial"] is True
    assert partial["stop_reason"] == "timeout"
    assert partial["tool_calls_made"] == 1
    assert partial["tool_history"] == ["read_current_code"]


@pytest.mark.anyio
async def test_verification_harness_short_circuits_on_successful_compile_tool(
    tmp_path,
    monkeypatch,
) -> None:
    """A successful compile_current_code tool result should complete the job immediately."""

    monkeypatch.setattr("src.prover.harness.suggest_fast_path_tactics", lambda _code: [])

    harness = VerificationHarness(
        driver=CompileSuccessDriver(),
        file_controller=ProofFileController(workspace_root=tmp_path),
        budget_tracker=BudgetTracker(),
    )
    result = await harness.verify(
        "import Mathlib\n\ntheorem provider_compile_success : True := by\n  sorry\n",
        "job_compile_success",
        max_steps=4,
    )

    assert result.status == "completed"
    assert result.result is not None
    assert result.result["compile"]["success"] is True
    assert result.result["tool_history"] == ["write_current_code", "compile_current_code"]


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
