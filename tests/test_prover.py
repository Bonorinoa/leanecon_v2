"""Verification harness tests for the Phase 3 implementation."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest

from lean_interact.interface import LeanError
from src.drivers.base import DriverConfig, DriverEvent, ToolCall, ToolResult
from src.drivers.registry import get_prover_driver
from src.prover.fast_path import repl_fast_path
from src.prover import VerificationHarness
from src.prover.file_controller import ProofFileController
from src.prover.tools import REPLToolDispatcher
from src.prover.tool_tracker import BudgetTracker


@pytest.mark.anyio
async def test_verification_harness_solves_simple_arithmetic(tmp_path, monkeypatch) -> None:
    """The local fast path should discharge easy arithmetic goals."""

    from src.prover import harness as harness_module

    monkeypatch.setattr(harness_module, "REPL_ENABLED", False)
    monkeypatch.setattr(harness_module, "LeanREPLSession", None)
    monkeypatch.setattr(harness_module, "suggest_fast_path_tactics", lambda _code: ["norm_num"])

    def fake_compile_check(lean_code: str, *, timeout=None, filename=None, check_axioms=False):
        _ = timeout
        _ = check_axioms
        success = "norm_num" in lean_code and filename == "job_arith_fast_1.lean"
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

    monkeypatch.setattr(harness_module, "compile_check", fake_compile_check)

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
    assert result.result["telemetry"]["lean_ms"] >= 0
    assert result.result["telemetry"]["provider_ms"] == 0


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
        return SimpleNamespace(state_id=1, goals=["⊢ goal"], is_solved=False)

    def apply_tactic(self, *args, timeout=None):
        _ = timeout
        if len(args) == 1:
            tactic = args[0]
        elif len(args) == 2:
            _, tactic = args
        else:
            raise TypeError("unexpected arguments")
        type(self).tactic_calls.append(tactic)
        self.call_count += 1
        self.tactic = tactic
        proof_status = "Incomplete: open goals remain" if self.call_count == 1 else "Completed"
        goals = ["⊢ goal"] if self.call_count == 1 else []
        return SimpleNamespace(
            has_errors=lambda: False,
            proof_status=proof_status,
            proof_state=self.call_count + 1,
            goals=goals,
            get_errors=lambda: [],
        )

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
    monkeypatch.setattr("src.prover.fast_path.suggest_fast_path_tactics", lambda _code: ["simp", "norm_num"])
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
    assert FakeLeanREPLSession.start_calls == 2
    assert FakeLeanREPLSession.tactic_calls == ["simp", "norm_num"]
    assert FakeLeanREPLSession.verify_calls == ["job_repl_fast_path_fast_2.lean"]
    assert compile_calls == []
    assert result.result["telemetry"]["lean_ms"] >= 0
    assert result.result["telemetry"]["provider_ms"] == 0


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
        return SimpleNamespace(state_id=1, goals=["⊢ goal"], is_solved=False)

    def apply_tactic(self, *args, timeout=None):
        _ = timeout
        if len(args) == 1:
            tactic = args[0]
        elif len(args) == 2:
            _, tactic = args
        else:
            raise TypeError("unexpected arguments")
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
    monkeypatch.setattr("src.prover.fast_path.suggest_fast_path_tactics", lambda _code: ["norm_num"])
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
    assert compile_calls == ["job_repl_fallback_fast_1.lean"]
    assert result.result["telemetry"]["lean_ms"] >= 0
    assert result.result["telemetry"]["provider_ms"] == 0
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
    from src.prover import harness as harness_module

    monkeypatch.setattr(harness_module, "REPL_ENABLED", False)
    monkeypatch.setattr(harness_module, "LeanREPLSession", None)
    monkeypatch.setattr(harness_module, "suggest_fast_path_tactics", lambda _code: [])

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
    assert result.result["telemetry"]["lean_ms"] >= 0
    assert result.result["telemetry"]["provider_ms"] >= 0
    assert (tmp_path / "checkpoints" / "job_provider_1001.lean").exists()
@pytest.mark.anyio
async def test_verification_harness_fails_cleanly_without_provider_key(
    tmp_path,
    monkeypatch,
) -> None:
    """When fast paths fail and no provider is configured, the harness should fail cleanly."""
    from src.prover import harness as harness_module

    monkeypatch.setattr(harness_module, "REPL_ENABLED", False)
    monkeypatch.setattr(harness_module, "LeanREPLSession", None)
    monkeypatch.setattr(harness_module, "suggest_fast_path_tactics", lambda _code: [])

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
    from src.prover import harness as harness_module

    monkeypatch.setattr(harness_module, "REPL_ENABLED", False)
    monkeypatch.setattr(harness_module, "LeanREPLSession", None)
    monkeypatch.setattr(harness_module, "suggest_fast_path_tactics", lambda _code: [])

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


class NormNumLeanREPLSession:
    """Fake REPL session that closes the theorem when norm_num is tried."""

    verify_calls: list[str] = []

    def __init__(self, *args, **kwargs):
        _ = args
        _ = kwargs
        self.theorem_with_sorry = ""

    def start_proof(self, theorem_with_sorry: str, *, timeout=None):
        _ = timeout
        self.theorem_with_sorry = theorem_with_sorry
        return SimpleNamespace(state_id=17, goals=["⊢ goal"], is_solved=False)

    def apply_tactic(self, *args, timeout=None):
        _ = timeout
        if len(args) == 1:
            tactic = args[0]
        elif len(args) == 2:
            _, tactic = args
        else:
            raise TypeError("unexpected arguments")
        if tactic == "norm_num":
            return SimpleNamespace(
                has_errors=lambda: False,
                proof_status="Completed",
                proof_state=18,
                goals=[],
                get_errors=lambda: [],
            )
        return SimpleNamespace(
            has_errors=lambda: False,
            proof_status="Incomplete: open goals remain",
            proof_state=17,
            goals=["⊢ goal"],
            get_errors=lambda: [],
        )

    def materialize_proof(self) -> str:
        return self.theorem_with_sorry.replace("sorry", "norm_num")

    def verify_materialized_proof(self, *, filename: str = "repl_verified.lean", timeout=None):
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
async def test_repl_fast_path_closes_trivial_proof():
    """The REPL fast path should close a norm_num-level theorem and verify it."""

    NormNumLeanREPLSession.verify_calls = []
    theorem = "import Mathlib\n\ntheorem repl_norm_num_demo : 1 + 1 = 2 := by\n  sorry\n"

    result = await repl_fast_path(
        NormNumLeanREPLSession(),
        theorem,
        max_attempts=6,
        job_id="job_norm_num",
    )

    assert result is not None
    assert result["success"] is True
    assert result["candidate_result"]["success"] is True
    assert NormNumLeanREPLSession.verify_calls == ["job_norm_num_fast_5.lean"]


class DispatcherLeanREPLSession:
    """Fake REPL session for dispatcher routing tests."""

    def __init__(self, *args, **kwargs):
        _ = args
        _ = kwargs
        self.theorem_with_sorry = ""
        self.tactic_calls: list[str] = []
        self._proof_state = SimpleNamespace(state_id=31, goals=["⊢ goal"], is_solved=False)

    @property
    def proof_state(self):
        return self._proof_state

    def get_goal_state(self, state_id=None):
        _ = state_id
        return self._proof_state

    def start_proof(self, theorem_with_sorry: str, *, timeout=None):
        _ = timeout
        self.theorem_with_sorry = theorem_with_sorry
        self._proof_state = SimpleNamespace(state_id=31, goals=["⊢ goal"], is_solved=False)
        return self._proof_state

    def apply_tactic(self, *args, timeout=None):
        _ = timeout
        if len(args) == 1:
            tactic = args[0]
        elif len(args) == 2:
            _, tactic = args
        else:
            raise TypeError("unexpected arguments")
        self.tactic_calls.append(tactic)
        self._proof_state = SimpleNamespace(state_id=32, goals=[], is_solved=True)
        return SimpleNamespace(
            has_errors=lambda: False,
            proof_status="Completed",
            proof_state=32,
            goals=[],
            get_errors=lambda: [],
        )

    def materialize_proof(self) -> str:
        if not self.tactic_calls:
            return self.theorem_with_sorry
        return self.theorem_with_sorry.replace("sorry", "trivial")


@pytest.mark.anyio
async def test_repl_dispatcher_routes_tool_calls(tmp_path):
    """The dispatcher should map compile_current_code to goal inspection and apply tactics through the REPL."""

    dispatcher = REPLToolDispatcher(
        repl=DispatcherLeanREPLSession(),
        theorem_code="import Mathlib\n\ntheorem dispatcher_demo : True := by\n  sorry\n",
        file_controller=ProofFileController(workspace_root=tmp_path),
        job_id="job_dispatcher",
    )

    init_result = await dispatcher.initialize()
    assert init_result["is_solved"] is False

    goal_result = dispatcher.handle_tool_call(ToolCall(id="call_goal", name="compile_current_code", arguments={}))
    assert goal_result.is_error is False
    assert "Current goals:" in goal_result.content

    tactic_result = dispatcher.handle_tool_call(
        ToolCall(id="call_apply", name="apply_tactic", arguments={"tactic": "trivial"})
    )
    assert tactic_result.is_error is False
    assert tactic_result.content == "Proof complete! All goals solved."
    assert dispatcher.tactic_history == ["trivial"]
    assert dispatcher.build_final_code().endswith("trivial\n") or "trivial" in dispatcher.build_final_code()


@pytest.mark.anyio
async def test_verification_harness_short_circuits_on_successful_compile_tool(
    tmp_path,
    monkeypatch,
) -> None:
    """A successful compile_current_code tool result should complete the job immediately."""
    from src.prover import harness as harness_module

    monkeypatch.setattr(harness_module, "REPL_ENABLED", False)
    monkeypatch.setattr(harness_module, "LeanREPLSession", None)
    monkeypatch.setattr(harness_module, "suggest_fast_path_tactics", lambda _code: [])

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
    assert result.result["telemetry"]["lean_ms"] >= 0
    assert result.result["telemetry"]["provider_ms"] >= 0


@pytest.mark.anyio
async def test_verification_harness_uses_budget_set_fast_path(tmp_path, monkeypatch) -> None:
    """Budget-set membership stubs should be closed by the local simpa tactic."""
    from src.prover import harness as harness_module

    monkeypatch.setattr(harness_module, "REPL_ENABLED", False)
    monkeypatch.setattr(harness_module, "LeanREPLSession", None)
    monkeypatch.setattr(
        harness_module,
        "suggest_fast_path_tactics",
        lambda _code: ["simpa [in_budget_set] using hbudget"],
    )

    def fake_compile_check(lean_code: str, *, timeout=None, filename=None, check_axioms=False):
        _ = timeout
        _ = check_axioms
        success = "simpa [in_budget_set] using hbudget" in lean_code and filename == "job_budget_fast_1.lean"
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

    monkeypatch.setattr(harness_module, "compile_check", fake_compile_check)

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
