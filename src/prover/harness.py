"""Provider-agnostic proving harness with local fast paths."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.config import REPL_ENABLED
from src.drivers.base import ProverDriver, ToolCall, ToolDefinition, ToolResult
from src.lean import LeanREPLSession, compile_check
from src.models import JobStatus
from src.prover.fast_path import repl_fast_path, replace_sorry_with_tactic, suggest_fast_path_tactics
from src.prover.file_controller import ProofFileController
from src.prover.goal_analyst import generate_goal_analyst_hint
from src.prover.prompts import (
    PROOF_SKETCH_SYSTEM_PROMPT,
    PROVER_SYSTEM_PROMPT,
    build_proof_sketch_user_prompt,
    build_prover_user_prompt,
)
from src.prover.tools import REPLToolDispatcher
from src.prover.tool_tracker import BudgetTracker
from src.search import search_claim


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_theorem_name(theorem_with_sorry: str) -> str:
    for line in theorem_with_sorry.splitlines():
        stripped = line.strip()
        if stripped.startswith(("theorem ", "lemma ")):
            parts = stripped.split()
            if len(parts) >= 2:
                return parts[1]
    return "anonymous_theorem"


@dataclass
class SpanRecorder:
    """Track Lean, provider, and orchestration time for one verification job."""

    started_at: float = field(default_factory=time.perf_counter)
    lean_ms: float = 0.0
    provider_ms: float = 0.0

    def record_lean(self, started_at: float) -> None:
        self.lean_ms += max(0.0, (time.perf_counter() - started_at) * 1000.0)

    def record_provider(self, started_at: float, *, lean_ms_during_span: float = 0.0) -> None:
        elapsed_ms = max(0.0, (time.perf_counter() - started_at) * 1000.0)
        self.provider_ms += max(0.0, elapsed_ms - lean_ms_during_span)

    def snapshot(self) -> dict[str, float]:
        total_ms = max(0.0, (time.perf_counter() - self.started_at) * 1000.0)
        orchestration_ms = max(0.0, total_ms - self.lean_ms - self.provider_ms)
        return {
            "lean_ms": round(self.lean_ms, 3),
            "provider_ms": round(self.provider_ms, 3),
            "orchestration_ms": round(orchestration_ms, 3),
        }


def _timed_compile_check(
    telemetry: SpanRecorder | None,
    lean_code: str,
    **kwargs: Any,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        return compile_check(lean_code, **kwargs)
    finally:
        if telemetry is not None:
            telemetry.record_lean(started_at)


def _attach_telemetry(result: dict[str, Any], telemetry: SpanRecorder) -> dict[str, Any]:
    payload = dict(result)
    payload["telemetry"] = telemetry.snapshot()
    return payload


def _repl_validation_result(repl_report: dict[str, Any]) -> dict[str, Any]:
    success = bool(repl_report.get("used"))
    fallback_reason = repl_report.get("fallback_reason")
    return {
        "success": success,
        "has_sorry": True,
        "axiom_warnings": [],
        "output": "",
        "errors": [] if success else ([fallback_reason] if fallback_reason else ["LeanInteract did not validate the theorem stub."]),
        "warnings": [],
        "stdout": "",
        "stderr": "",
        "exit_code": 0 if success else 1,
        "source": "repl_start_proof",
    }


async def _generate_proof_sketch(
    driver: ProverDriver,
    theorem_with_sorry: str,
    on_progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> str | None:
    """Generate a single informal proof sketch before the prover loop."""

    def reject_tool_call(tool_call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call.id,
            "Proof sketch generation does not use tools.",
            is_error=True,
        )

    sketch_chunks: list[str] = []
    try:
        async for event in driver.prove(
            system_prompt=PROOF_SKETCH_SYSTEM_PROMPT,
            user_prompt=build_proof_sketch_user_prompt(theorem_with_sorry),
            tools=[],
            on_tool_call=reject_tool_call,
            max_steps=1,
        ):
            if event.type == "assistant":
                content = event.data.get("content") if isinstance(event.data, dict) else None
                if isinstance(content, str) and content.strip():
                    sketch_chunks.append(content.strip())
                continue

            if event.type == "done":
                content = event.data.get("content") if isinstance(event.data, dict) else None
                if isinstance(content, str) and content.strip():
                    sketch_chunks.append(content.strip())
                break

            if event.type == "error":
                if on_progress is not None:
                    on_progress("proof_sketch_fallback", {"reason": str(event.data)})
                return None

            if event.type == "tool_call":
                if on_progress is not None:
                    on_progress(
                        "proof_sketch_fallback",
                        {"reason": "Proof sketch generation attempted an unexpected tool call."},
                    )
                return None
    except Exception as exc:
        if on_progress is not None:
            on_progress("proof_sketch_fallback", {"reason": f"{type(exc).__name__}: {exc}"})
        return None

    sketch = "\n".join(chunk for chunk in sketch_chunks if chunk).strip()
    if sketch and on_progress is not None:
        on_progress("proof_sketch", {"sketch": sketch})
    return sketch or None


@dataclass
class VerificationHarness:
    """Provider-backed proving orchestration with deterministic local fallbacks."""

    driver: ProverDriver
    file_controller: ProofFileController
    budget_tracker: BudgetTracker

    async def verify(
        self,
        theorem_with_sorry: str,
        job_id: str,
        on_progress: Callable[[str, dict[str, Any]], None] | None = None,
        *,
        max_steps: int = 16,
    ) -> JobStatus:
        """Verify a theorem stub, trying local tactics before provider calls."""

        telemetry = SpanRecorder()
        created_at = _utc_now()
        theorem_name = _extract_theorem_name(theorem_with_sorry)
        current_code = theorem_with_sorry
        self.file_controller.initialize(job_id, theorem_with_sorry)
        if on_progress:
            on_progress("initialize", {"theorem": theorem_name})

        initial_check: dict[str, Any] | None = None
        repl_validation_check: dict[str, Any] | None = None
        repl_enabled = REPL_ENABLED and LeanREPLSession is not None

        if on_progress:
            on_progress(
                "initial_compile",
                {"theorem": theorem_name, "mode": "repl_start_proof" if repl_enabled else "compile_check"},
            )
        if not repl_enabled:
            initial_check = _timed_compile_check(
                telemetry,
                current_code,
                filename=f"{job_id}_initial.lean",
            )
            if initial_check["success"]:
                return JobStatus(
                    id=job_id,
                    status="completed",
                    created_at=created_at,
                    updated_at=_utc_now(),
                    result=_attach_telemetry(
                        {
                            "status": "verified",
                            "theorem": theorem_name,
                            "verified_code": current_code,
                            "compile": initial_check,
                            "attempts": [],
                            "tool_history": [],
                            "tool_budget": self.budget_tracker.snapshot(),
                        },
                        telemetry,
                    ),
                    error=None,
                )

            if initial_check["errors"]:
                return JobStatus(
                    id=job_id,
                    status="failed",
                    created_at=created_at,
                    updated_at=_utc_now(),
                    result=_attach_telemetry(
                        {
                            "status": "failed",
                            "theorem": theorem_name,
                            "compile": initial_check,
                            "tool_history": [],
                            "tool_budget": self.budget_tracker.snapshot(),
                        },
                        telemetry,
                    ),
                    error="Initial theorem did not compile as a valid theorem stub.",
                )

        attempts: list[dict[str, Any]] = []
        fast_path_tactics = suggest_fast_path_tactics(current_code)
        repl_report: dict[str, Any] = {
            "used": False,
            "success": False,
            "attempts": [],
            "fallback_reason": None,
            "candidate_code": None,
            "candidate_result": None,
        }

        if repl_enabled:
            try:
                with LeanREPLSession() as repl:
                    fast_path_started_at = time.perf_counter()
                    try:
                        repl_report = await repl_fast_path(
                            repl,
                            current_code,
                            max_attempts=max_steps,
                            job_id=job_id,
                        ) or repl_report
                    finally:
                        telemetry.record_lean(fast_path_started_at)
                    if repl_report["attempts"]:
                        attempts.extend(repl_report["attempts"])
                    if on_progress:
                        on_progress(
                            "repl_fast_path",
                            {
                                "success": repl_report["success"],
                                "attempts": repl_report["attempts"],
                                "fallback_reason": repl_report["fallback_reason"],
                            },
                        )
                    if repl_report["success"]:
                        candidate = repl_report["candidate_code"]
                        candidate_result = repl_report["candidate_result"]
                        if candidate is None or candidate_result is None:
                            raise RuntimeError("LeanInteract reported success without a materialized proof.")
                        self.file_controller.write_current_code(job_id, candidate)
                        self.file_controller.checkpoint(job_id, len(repl_report["attempts"]))
                        return JobStatus(
                            id=job_id,
                            status="completed",
                            created_at=created_at,
                            updated_at=_utc_now(),
                            result=_attach_telemetry(
                                {
                                    "status": "verified",
                                    "theorem": theorem_name,
                                    "verified_code": candidate,
                                    "compile": candidate_result,
                                    "attempts": attempts,
                                    "repl_fast_path": repl_report,
                                    "tool_history": list(self.budget_tracker.tool_history),
                                    "tool_budget": self.budget_tracker.snapshot(),
                                },
                                telemetry,
                            ),
                            error=None,
                        )
            except Exception as exc:
                repl_report["fallback_reason"] = f"{type(exc).__name__}: {exc}"
                if on_progress:
                    on_progress("repl_fast_path_fallback", {"reason": repl_report["fallback_reason"]})

            repl_validation_check = _repl_validation_result(repl_report)

        # --- NEW FAST-PATH BYPASS ---
        # If the REPL is enabled and already tried the fast path, skip the slow compile fallback
        if REPL_ENABLED and repl_report.get("used"):
            pass 
        elif not repl_report.get("used") or repl_report.get("fallback_reason"):
            for step, tactic in enumerate(fast_path_tactics, start=1):
                candidate = replace_sorry_with_tactic(current_code, tactic)
                if candidate is None:
                    continue
                self.file_controller.write_current_code(job_id, candidate)
                self.file_controller.checkpoint(job_id, step)
                if on_progress:
                    on_progress("fast_path_compile", {"step": step, "tactic": tactic})
                candidate_result = _timed_compile_check(
                    telemetry,
                    candidate,
                    filename=f"{job_id}_fast_{step}.lean",
                )
                attempts.append(
                    {
                        "step": step,
                        "mode": "compile_check_fast_path",
                        "tactic": tactic,
                        "success": candidate_result["success"],
                        "errors": candidate_result["errors"],
                    }
                )
                if on_progress:
                    on_progress(
                        "fast_path",
                        {"step": step, "tactic": tactic, "success": candidate_result["success"]},
                    )
                if candidate_result["success"]:
                    return JobStatus(
                        id=job_id,
                        status="completed",
                        created_at=created_at,
                        updated_at=_utc_now(),
                        result=_attach_telemetry(
                            {
                                "status": "verified",
                                "theorem": theorem_name,
                                "verified_code": candidate,
                                "compile": candidate_result,
                                "attempts": attempts,
                                "repl_fast_path": repl_report,
                                "tool_history": list(self.budget_tracker.tool_history),
                                "tool_budget": self.budget_tracker.snapshot(),
                            },
                            telemetry,
                        ),
                        error=None,
                    )

        proof_sketch: str | None = None
        sketch_started_at = time.perf_counter()
        try:
            proof_sketch = await _generate_proof_sketch(self.driver, theorem_with_sorry, on_progress)
        finally:
            if telemetry is not None:
                telemetry.record_provider(sketch_started_at)

        repl_provider_result: JobStatus | None = None
        if repl_enabled:
            try:
                with LeanREPLSession() as repl:
                    repl_provider_result = await self._provider_attempt(
                        job_id,
                        theorem_with_sorry,
                        on_progress,
                        proof_sketch=proof_sketch,
                        max_steps=max_steps,
                        repl=repl,
                        telemetry=telemetry,
                    )
                    if repl_provider_result is not None and repl_provider_result.status == "completed":
                        return repl_provider_result
            except Exception as exc:
                if on_progress:
                    on_progress("repl_provider_fallback", {"reason": f"{type(exc).__name__}: {exc}"})

        provider_result = await self._provider_attempt(
            job_id,
            theorem_with_sorry,
            on_progress,
            proof_sketch=proof_sketch,
            max_steps=max_steps,
            telemetry=telemetry,
        )
        if provider_result is not None:
            return provider_result

        if on_progress:
            on_progress("provider_finalize", {"theorem": theorem_name})
        compile_snapshot = initial_check if initial_check is not None else repl_validation_check or {
            "success": False,
            "has_sorry": True,
            "axiom_warnings": [],
            "output": "",
            "errors": ["Fast-path proving failed before a compile check could be run."],
            "warnings": [],
            "stdout": "",
            "stderr": "",
            "exit_code": 1,
        }
        return JobStatus(
            id=job_id,
            status="failed",
            created_at=created_at,
            updated_at=_utc_now(),
            result=_attach_telemetry(
                {
                    "status": "failed",
                    "theorem": theorem_name,
                    "compile": compile_snapshot,
                    "attempts": attempts,
                    "repl_fast_path": repl_report,
                    "tool_history": list(self.budget_tracker.tool_history),
                    "tool_budget": self.budget_tracker.snapshot(),
                },
                telemetry,
            ),
            error="Fast-path proving failed and no provider-backed proof was available.",
        )

    async def _provider_attempt(
        self,
        job_id: str,
        theorem_with_sorry: str,
        on_progress: Callable[[str, dict[str, Any]], None] | None,
        *,
        proof_sketch: str | None = None,
        max_steps: int,
        repl: LeanREPLSession | None = None,
        repl_dispatcher: REPLToolDispatcher | None = None,
        telemetry: SpanRecorder | None = None,
    ) -> JobStatus | None:
        """Use the configured provider for tool-mediated proof search."""

        theorem_name = _extract_theorem_name(theorem_with_sorry)
        created_at = _utc_now()
        attempts: list[dict[str, Any]] = []
        driver_failed = False
        driver_error = ""
        checkpoint_step = 1000
        provider_started_at = time.perf_counter()
        lean_ms_before_provider = telemetry.lean_ms if telemetry is not None else 0.0

        def build_status(
            status: str,
            result: dict[str, Any],
            *,
            error: str | None = None,
        ) -> JobStatus:
            return JobStatus(
                id=job_id,
                status=status,
                created_at=created_at,
                updated_at=_utc_now(),
                result=_attach_telemetry(result, telemetry) if telemetry is not None else result,
                error=error,
            )

        try:
            if repl_dispatcher is None and repl is not None:
                repl_dispatcher = REPLToolDispatcher(
                    repl=repl,
                    theorem_code=theorem_with_sorry,
                    file_controller=self.file_controller,
                    job_id=job_id,
                )
                repl_initialized_at = time.perf_counter()
                try:
                    await repl_dispatcher.initialize()
                finally:
                    if telemetry is not None:
                        telemetry.record_lean(repl_initialized_at)

            def on_tool_call(tool_call: ToolCall) -> ToolResult:
                nonlocal checkpoint_step
                if not self.budget_tracker.can_continue():
                    return ToolResult(tool_call.id, "Tool budget exhausted.", is_error=True)

                self.budget_tracker.record(tool_call.name)
                if repl_dispatcher is not None and tool_call.name in {
                    "read_current_code",
                    "compile_current_code",
                    "get_goals",
                    "write_current_code",
                    "apply_tactic",
                }:
                    lean_started_at = time.perf_counter()
                    result: ToolResult
                    try:
                        result = repl_dispatcher.handle_tool_call(tool_call)
                    finally:
                        if telemetry is not None:
                            telemetry.record_lean(lean_started_at)

                    if tool_call.name == "apply_tactic" and result.is_error:
                        context = repl_dispatcher.get_analysis_context()
                        hint = generate_goal_analyst_hint(
                            tactic=str(tool_call.arguments.get("tactic", "")).strip(),
                            lean_error=result.content,
                            goals=list(context.get("goals", [])),
                            tactic_history=list(context.get("tactic_history", [])),
                        )
                        if hint:
                            return ToolResult(
                                tool_call.id,
                                f"{result.content}\n\nGoal Analyst Hint: {hint}",
                                is_error=True,
                            )
                    return result

                if tool_call.name == "read_current_code":
                    return ToolResult(tool_call.id, self.file_controller.read_current_code(job_id))
                if tool_call.name == "compile_current_code":
                    current_code = self.file_controller.read_current_code(job_id)
                    compile_result = _timed_compile_check(
                        telemetry,
                        current_code,
                        filename=f"{job_id}_tool_compile.lean",
                    )
                    return ToolResult(tool_call.id, json.dumps(compile_result, indent=2, sort_keys=True))
                if tool_call.name == "search":
                    query = str(tool_call.arguments.get("query", "")).strip()
                    search_result = search_claim(query or theorem_with_sorry)
                    return ToolResult(tool_call.id, search_result.model_dump_json(indent=2))
                if tool_call.name == "write_current_code":
                    new_code = str(tool_call.arguments.get("theorem_code", "")).strip()
                    if not new_code:
                        return ToolResult(tool_call.id, "Missing theorem_code.", is_error=True)
                    self.file_controller.write_current_code(job_id, new_code)
                    checkpoint_step += 1
                    self.file_controller.checkpoint(job_id, checkpoint_step)
                    return ToolResult(
                        tool_call.id,
                        "Updated theorem code and saved a checkpoint. Run compile_current_code next.",
                    )
                if tool_call.name == "apply_tactic":
                    tactic = str(tool_call.arguments.get("tactic", "")).strip()
                    candidate = replace_sorry_with_tactic(
                        self.file_controller.read_current_code(job_id),
                        tactic,
                    )
                    if candidate is None:
                        return ToolResult(tool_call.id, "No standalone sorry found.", is_error=True)
                    self.file_controller.write_current_code(job_id, candidate)
                    checkpoint_step += 1
                    self.file_controller.checkpoint(job_id, checkpoint_step)
                    return ToolResult(
                        tool_call.id,
                        (
                            "Applied tactic candidate and saved a checkpoint. "
                            "Run compile_current_code next."
                        ),
                    )
                return ToolResult(tool_call.id, f"Unknown tool: {tool_call.name}", is_error=True)

            tools = [
                ToolDefinition(
                    name="read_current_code",
                    description="Read the current Lean theorem file under repair.",
                    parameters={"type": "object", "properties": {}, "additionalProperties": False},
                ),
                ToolDefinition(
                    name="compile_current_code",
                    description="Inspect the current REPL goal state or compile the current Lean theorem file.",
                    parameters={"type": "object", "properties": {}, "additionalProperties": False},
                ),
                ToolDefinition(
                    name="get_goals",
                    description="Inspect the current REPL goal state.",
                    parameters={"type": "object", "properties": {}, "additionalProperties": False},
                ),
                ToolDefinition(
                    name="search",
                    description="Run deterministic LeanEcon retrieval on a subquery.",
                    parameters={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                ),
                ToolDefinition(
                    name="write_current_code",
                    description="Replace the current theorem file with new Lean code.",
                    parameters={
                        "type": "object",
                        "properties": {"theorem_code": {"type": "string"}},
                        "required": ["theorem_code"],
                        "additionalProperties": False,
                    },
                ),
                ToolDefinition(
                    name="apply_tactic",
                    description="Apply one tactic to the active REPL proof state or rewrite the current file.",
                    parameters={
                        "type": "object",
                        "properties": {"tactic": {"type": "string"}},
                        "required": ["tactic"],
                        "additionalProperties": False,
                    },
                ),
            ]

            if on_progress:
                on_progress(
                    "provider_dispatch",
                    {
                        "max_steps": max_steps,
                        "budget": self.budget_tracker.snapshot(),
                    },
                )

            async for event in self.driver.prove(
                system_prompt=PROVER_SYSTEM_PROMPT,
                user_prompt=build_prover_user_prompt(theorem_with_sorry, proof_sketch=proof_sketch),
                tools=tools,
                on_tool_call=on_tool_call,
                max_steps=max_steps,
            ):
                attempts.append({"event": event.type, "data": event.data})
                if on_progress:
                    on_progress("provider", {"event_type": event.type, "data": event.data})
                if repl_dispatcher is None and event.type == "tool_result" and isinstance(event.data, dict):
                    if event.data.get("name") == "compile_current_code":
                        content = event.data.get("content")
                        if isinstance(content, str):
                            try:
                                compile_result = json.loads(content)
                            except json.JSONDecodeError:
                                compile_result = None
                            if isinstance(compile_result, dict) and compile_result.get("success"):
                                current_code = self.file_controller.read_current_code(job_id)
                                return build_status(
                                    "completed",
                                    {
                                        "status": "verified",
                                        "theorem": theorem_name,
                                        "verified_code": current_code,
                                        "compile": compile_result,
                                        "attempts": attempts,
                                        "tool_history": list(self.budget_tracker.tool_history),
                                        "tool_budget": self.budget_tracker.snapshot(),
                                    },
                                )
                if event.type == "error":
                    driver_failed = True
                    driver_error = str(event.data)
                    break
                if event.type == "done":
                    break

            current_code = (
                repl_dispatcher.build_final_code()
                if repl_dispatcher is not None
                else self.file_controller.read_current_code(job_id)
            )
            final_check = _timed_compile_check(
                telemetry,
                current_code,
                filename=f"{job_id}_provider_final.lean",
            )
            if final_check["success"]:
                return build_status(
                    "completed",
                    {
                        "status": "verified",
                        "theorem": theorem_name,
                        "verified_code": current_code,
                        "compile": final_check,
                        "attempts": attempts,
                        "tool_history": list(self.budget_tracker.tool_history),
                        "tool_budget": self.budget_tracker.snapshot(),
                    },
                )

            if driver_failed or final_check["errors"]:
                return build_status(
                    "failed",
                    {
                        "status": "failed",
                        "theorem": theorem_name,
                        "compile": final_check,
                        "attempts": attempts,
                        "tool_history": list(self.budget_tracker.tool_history),
                        "tool_budget": self.budget_tracker.snapshot(),
                    },
                    error=driver_error or "Provider-backed proof search did not close the theorem.",
                )

            return None
        finally:
            if telemetry is not None:
                telemetry.record_provider(
                    provider_started_at,
                    lean_ms_during_span=max(0.0, telemetry.lean_ms - lean_ms_before_provider),
                )
