"""REPL-backed tool dispatch helpers for the prover harness."""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from typing import Any

from lean_interact.interface import LeanError

from src.config import DEFAULT_DRIVER
from src.drivers.base import ToolCall, ToolResult
from src.drivers.provider_config import provider_driver_config
from src.drivers.registry import get_formalizer_driver
from src.lean import LeanREPLSession
from src.prover.file_controller import ProofFileController
from src.prover.prompts import (
    build_syntax_fixer_system_prompt,
    build_syntax_fixer_user_prompt,
)


_SYNTAX_RETRY_MARKERS = (
    "unknown identifier",
    "unknown constant",
    "unknown module prefix",
    "unknown notation",
    "invalid syntax",
    "unexpected token",
    "unexpected end of input",
    "macro expected",
    "expected ')'",
    "expected ']'",
    "expected '}'",
    "expected ':='",
    "expected term",
    "expected expression",
    "expected identifier",
    "expected command",
)
_SYNTAX_FIXER_MAX_TOKENS = 256


def _format_goals(goals: list[str]) -> str:
    if not goals:
        return "All goals solved."
    lines = ["Current goals:"]
    for index, goal in enumerate(goals, start=1):
        lines.append(f"  {index}. {goal}")
    return "\n".join(lines)


def _collect_error_messages(response: Any) -> list[str]:
    if isinstance(response, LeanError):
        return [response.message]
    if hasattr(response, "get_errors"):
        return [message.data for message in response.get_errors() if getattr(message, "data", "")]
    return []


def _is_retryable_syntax_error(error_messages: list[str]) -> bool:
    lowered = "\n".join(error_messages).lower()
    return any(marker in lowered for marker in _SYNTAX_RETRY_MARKERS)


def _syntax_fixer_driver() -> Any | None:
    config = provider_driver_config(
        driver_name=DEFAULT_DRIVER,
        temperature=0.0,
        max_tokens=_SYNTAX_FIXER_MAX_TOKENS,
        timeout=60.0,
    )
    if not config.api_key:
        return None
    try:
        return get_formalizer_driver(DEFAULT_DRIVER, config)
    except ValueError:
        return None


def _strip_fences(raw_output: str) -> str:
    lines = raw_output.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _retry_with_syntax_fixer(tactic: str, error_messages: list[str], goals: list[str]) -> str | None:
    driver = _syntax_fixer_driver()
    if driver is None:
        return None

    system_prompt = build_syntax_fixer_system_prompt()
    user_prompt = build_syntax_fixer_user_prompt(tactic, error_messages, goals)
    outcome: dict[str, str | None] = {"repaired": None}

    def _worker() -> None:
        try:
            outcome["repaired"] = asyncio.run(
                driver.formalize(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=_SYNTAX_FIXER_MAX_TOKENS,
                )
            )
        except Exception:
            outcome["repaired"] = None

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    repaired = outcome["repaired"]
    if not repaired:
        return None
    repaired = _strip_fences(repaired)
    if not repaired or repaired == tactic.strip():
        return None
    return repaired


@dataclass
class REPLToolDispatcher:
    """Dispatch prover tool calls through a live LeanInteract session."""

    repl: Any
    theorem_code: str
    file_controller: ProofFileController | None = None
    job_id: str | None = None
    current_state_id: int | None = None
    tactic_history: list[str] = field(default_factory=list)
    goal_history: list[list[str]] = field(default_factory=list)

    async def initialize(self) -> dict[str, Any]:
        state = self.repl.start_proof(self.theorem_code)
        self.current_state_id = state.state_id
        self.goal_history.append(list(state.goals))
        self._sync_current_code()
        return {
            "goals": list(state.goals),
            "is_solved": state.is_solved,
            "message": f"Proof initialized with {len(state.goals)} goal(s).",
        }

    def handle_tool_call(self, tool_call: ToolCall) -> ToolResult:
        if tool_call.name == "read_current_code":
            return ToolResult(tool_call.id, self._read_current_code())
        if tool_call.name in {"compile_current_code", "get_goals"}:
            return ToolResult(tool_call.id, self._get_goals())
        if tool_call.name == "write_current_code":
            return self._write_current_code(tool_call)
        if tool_call.name == "apply_tactic":
            tactic = str(tool_call.arguments.get("tactic", "")).strip()
            if not tactic:
                return ToolResult(tool_call.id, "Missing tactic.", is_error=True)
            return self._apply_tactic(tool_call.id, tactic)
        return ToolResult(tool_call.id, f"Unknown tool: {tool_call.name}", is_error=True)

    def build_final_code(self) -> str:
        if self.file_controller is not None and self.job_id is not None:
            return self.file_controller.read_current_code(self.job_id)
        return self.repl.materialize_proof()

    def _read_current_code(self) -> str:
        if self.file_controller is not None and self.job_id is not None:
            return self.file_controller.read_current_code(self.job_id)
        return self.repl.materialize_proof()

    def _get_goals(self) -> str:
        state = self._current_state()
        return _format_goals(list(state.goals))

    def get_analysis_context(self) -> dict[str, Any]:
        state = self._current_state()
        goals = list(getattr(state, "goals", []) or [])
        if not goals and self.goal_history:
            goals = list(self.goal_history[-1])
        return {
            "goals": goals,
            "tactic_history": list(self.tactic_history),
        }

    def _apply_tactic(self, call_id: str, tactic: str) -> ToolResult:
        state = self._current_state()
        response = self.repl.apply_tactic(state.state_id, tactic)
        if isinstance(response, LeanError) or response.has_errors():
            error_messages = _collect_error_messages(response)
            repaired_result = self._retry_repaired_tactic(state.state_id, tactic, error_messages, list(state.goals), call_id)
            if repaired_result is not None:
                return repaired_result
            if isinstance(response, LeanError):
                content = "\n".join(error_messages) if error_messages else response.message
            else:
                content = "\n".join(error_messages) if error_messages else f"Tactic failed: {tactic}"
            return ToolResult(call_id, content, is_error=True)

        self.current_state_id = response.proof_state
        self.tactic_history.append(tactic)
        self.goal_history.append(list(response.goals))
        self._sync_current_code()

        if getattr(response, "proof_status", "") == "Completed":
            return ToolResult(call_id, "Proof complete! All goals solved.")

        return ToolResult(call_id, _format_goals(list(response.goals)))

    def _retry_repaired_tactic(
        self,
        state_id: int,
        tactic: str,
        error_messages: list[str],
        goals: list[str],
        call_id: str,
    ) -> ToolResult | None:
        if not _is_retryable_syntax_error(error_messages):
            return None

        repaired_tactic = _retry_with_syntax_fixer(tactic, error_messages, goals)
        if repaired_tactic is None:
            return None

        retry_response = self.repl.apply_tactic(state_id, repaired_tactic)
        if isinstance(retry_response, LeanError) or retry_response.has_errors():
            return None

        self.current_state_id = retry_response.proof_state
        self.tactic_history.append(repaired_tactic)
        self.goal_history.append(list(retry_response.goals))
        self._sync_current_code()

        if getattr(retry_response, "proof_status", "") == "Completed":
            return ToolResult(call_id, "Proof complete! All goals solved.")

        return ToolResult(call_id, _format_goals(list(retry_response.goals)))

    def _write_current_code(self, tool_call: ToolCall) -> ToolResult:
        new_code = str(tool_call.arguments.get("theorem_code", "")).strip()
        if not new_code:
            return ToolResult(tool_call.id, "Missing theorem_code.", is_error=True)

        self.theorem_code = new_code
        if self.file_controller is not None and self.job_id is not None:
            self.file_controller.write_current_code(self.job_id, new_code)

        try:
            state = self.repl.start_proof(new_code)
        except Exception as exc:
            return ToolResult(tool_call.id, str(exc), is_error=True)

        self.current_state_id = state.state_id
        self.tactic_history.clear()
        self.goal_history = [list(state.goals)]
        self._sync_current_code()
        return ToolResult(tool_call.id, "Updated theorem code and restarted the REPL proof.")

    def _current_state(self):
        if self.current_state_id is None:
            raise RuntimeError("Call initialize() before using REPL tool calls.")

        if hasattr(self.repl, "get_goal_state"):
            state = self.repl.get_goal_state(self.current_state_id)
        else:
            state = getattr(self.repl, "proof_state", None)
            if state is None:
                raise RuntimeError("The active REPL state is unavailable.")
            if getattr(state, "state_id", None) != self.current_state_id:
                raise RuntimeError("The active REPL state does not match the dispatcher state.")

        return state

    def _sync_current_code(self) -> None:
        if self.file_controller is None or self.job_id is None:
            return
        self.file_controller.write_current_code(self.job_id, self.repl.materialize_proof())
        if self.tactic_history:
            self.file_controller.checkpoint(self.job_id, len(self.tactic_history))
