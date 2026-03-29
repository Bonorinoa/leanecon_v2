"""Provider-agnostic proving harness with local fast paths."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.drivers.base import ProverDriver, ToolCall, ToolDefinition, ToolResult
from src.lean import compile_check
from src.models import JobStatus
from src.prover.fast_path import replace_sorry_with_tactic, suggest_fast_path_tactics
from src.prover.file_controller import ProofFileController
from src.prover.prompts import PROVER_SYSTEM_PROMPT, build_prover_user_prompt
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

        created_at = _utc_now()
        theorem_name = _extract_theorem_name(theorem_with_sorry)
        current_code = theorem_with_sorry
        self.file_controller.initialize(job_id, theorem_with_sorry)
        if on_progress:
            on_progress("initialize", {"theorem": theorem_name})

        if on_progress:
            on_progress("initial_compile", {"theorem": theorem_name})
        initial_check = compile_check(current_code, filename=f"{job_id}_initial.lean")
        if initial_check["success"]:
            return JobStatus(
                id=job_id,
                status="completed",
                created_at=created_at,
                updated_at=_utc_now(),
                result={
                    "status": "verified",
                    "theorem": theorem_name,
                    "verified_code": current_code,
                    "compile": initial_check,
                    "attempts": [],
                    "tool_history": [],
                    "tool_budget": self.budget_tracker.snapshot(),
                },
                error=None,
            )

        if initial_check["errors"]:
            return JobStatus(
                id=job_id,
                status="failed",
                created_at=created_at,
                updated_at=_utc_now(),
                result={
                    "status": "failed",
                    "theorem": theorem_name,
                    "compile": initial_check,
                    "tool_history": [],
                    "tool_budget": self.budget_tracker.snapshot(),
                },
                error="Initial theorem did not compile as a valid theorem stub.",
            )

        attempts: list[dict[str, Any]] = []
        for step, tactic in enumerate(suggest_fast_path_tactics(current_code), start=1):
            candidate = replace_sorry_with_tactic(current_code, tactic)
            if candidate is None:
                continue
            self.file_controller.write_current_code(job_id, candidate)
            self.file_controller.checkpoint(job_id, step)
            if on_progress:
                on_progress("fast_path_compile", {"step": step, "tactic": tactic})
            candidate_result = compile_check(candidate, filename=f"{job_id}_fast_{step}.lean")
            attempts.append(
                {
                    "step": step,
                    "mode": "fast_path",
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
                    result={
                        "status": "verified",
                        "theorem": theorem_name,
                        "verified_code": candidate,
                        "compile": candidate_result,
                        "attempts": attempts,
                        "tool_history": list(self.budget_tracker.tool_history),
                        "tool_budget": self.budget_tracker.snapshot(),
                    },
                    error=None,
                )

        provider_result = await self._provider_attempt(
            job_id,
            theorem_with_sorry,
            on_progress,
            max_steps=max_steps,
        )
        if provider_result is not None:
            return provider_result

        if on_progress:
            on_progress("provider_finalize", {"theorem": theorem_name})
        return JobStatus(
            id=job_id,
            status="failed",
            created_at=created_at,
            updated_at=_utc_now(),
            result={
                "status": "failed",
                "theorem": theorem_name,
                "compile": initial_check,
                "attempts": attempts,
                "tool_history": list(self.budget_tracker.tool_history),
                "tool_budget": self.budget_tracker.snapshot(),
            },
            error="Fast-path proving failed and no provider-backed proof was available.",
        )

    async def _provider_attempt(
        self,
        job_id: str,
        theorem_with_sorry: str,
        on_progress: Callable[[str, dict[str, Any]], None] | None,
        *,
        max_steps: int,
    ) -> JobStatus | None:
        """Use the configured provider for tool-mediated proof search."""

        theorem_name = _extract_theorem_name(theorem_with_sorry)
        created_at = _utc_now()
        attempts: list[dict[str, Any]] = []
        driver_failed = False
        driver_error = ""
        checkpoint_step = 1000

        def on_tool_call(tool_call: ToolCall) -> ToolResult:
            nonlocal checkpoint_step
            if not self.budget_tracker.can_continue():
                return ToolResult(tool_call.id, "Tool budget exhausted.", is_error=True)

            self.budget_tracker.record(tool_call.name)
            if tool_call.name == "read_current_code":
                return ToolResult(tool_call.id, self.file_controller.read_current_code(job_id))
            if tool_call.name == "compile_current_code":
                current_code = self.file_controller.read_current_code(job_id)
                result = compile_check(current_code, filename=f"{job_id}_tool_compile.lean")
                return ToolResult(tool_call.id, json.dumps(result, indent=2, sort_keys=True))
            if tool_call.name == "search":
                query = str(tool_call.arguments.get("query", "")).strip()
                result = search_claim(query or theorem_with_sorry)
                return ToolResult(tool_call.id, result.model_dump_json(indent=2))
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
                description="Compile the current Lean theorem file and inspect diagnostics.",
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
                description="Replace the first `sorry` with a tactic candidate.",
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
            user_prompt=build_prover_user_prompt(theorem_with_sorry),
            tools=tools,
            on_tool_call=on_tool_call,
            max_steps=max_steps,
        ):
            attempts.append({"event": event.type, "data": event.data})
            if on_progress:
                on_progress("provider", {"event_type": event.type, "data": event.data})
            if event.type == "tool_result" and isinstance(event.data, dict):
                if event.data.get("name") == "compile_current_code":
                    content = event.data.get("content")
                    if isinstance(content, str):
                        try:
                            compile_result = json.loads(content)
                        except json.JSONDecodeError:
                            compile_result = None
                        if isinstance(compile_result, dict) and compile_result.get("success"):
                            current_code = self.file_controller.read_current_code(job_id)
                            return JobStatus(
                                id=job_id,
                                status="completed",
                                created_at=created_at,
                                updated_at=_utc_now(),
                                result={
                                    "status": "verified",
                                    "theorem": theorem_name,
                                    "verified_code": current_code,
                                    "compile": compile_result,
                                    "attempts": attempts,
                                    "tool_history": list(self.budget_tracker.tool_history),
                                    "tool_budget": self.budget_tracker.snapshot(),
                                },
                                error=None,
                            )
            if event.type == "error":
                driver_failed = True
                driver_error = str(event.data)
                break
            if event.type == "done":
                break

        current_code = self.file_controller.read_current_code(job_id)
        final_check = compile_check(current_code, filename=f"{job_id}_provider_final.lean")
        if final_check["success"]:
            return JobStatus(
                id=job_id,
                status="completed",
                created_at=created_at,
                updated_at=_utc_now(),
                result={
                    "status": "verified",
                    "theorem": theorem_name,
                    "verified_code": current_code,
                    "compile": final_check,
                    "attempts": attempts,
                    "tool_history": list(self.budget_tracker.tool_history),
                    "tool_budget": self.budget_tracker.snapshot(),
                },
                error=None,
            )

        if driver_failed or final_check["errors"]:
            return JobStatus(
                id=job_id,
                status="failed",
                created_at=created_at,
                updated_at=_utc_now(),
                result={
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
