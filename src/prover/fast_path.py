"""Local tactic shortcuts for cheap proving attempts."""

from __future__ import annotations

import re
from typing import Any

from lean_interact.interface import LeanError

from src.lean import LeanREPLSession


def replace_sorry_with_tactic(theorem_with_sorry: str, tactic: str) -> str | None:
    """Replace the first standalone `sorry` with an indented tactic block."""

    lines = theorem_with_sorry.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped != "sorry":
            continue
        indent = line[: len(line) - len(line.lstrip())] or "  "
        tactic_lines = [f"{indent}{part}" for part in tactic.splitlines()]
        return "\n".join(lines[:index] + tactic_lines + lines[index + 1 :])
    return None


def suggest_fast_path_tactics(theorem_with_sorry: str) -> list[str]:
    """Return deterministic tactic suggestions based on obvious patterns."""

    lowered = theorem_with_sorry.lower()
    suggestions: list[str] = ["simpa", "aesop", "simp", "rfl", "norm_num", "exact?"]

    if " true " in f" {lowered} ":
        suggestions.append("trivial")
    if "hspend" in theorem_with_sorry:
        suggestions.append("simpa using hspend")
    if " = " in theorem_with_sorry:
        suggestions.append("rfl")
        suggestions.append("ring")
        suggestions.append("field_simp")
    if "∧" in theorem_with_sorry or "/\\" in theorem_with_sorry:
        suggestions.append("constructor")
    if "in_budget_set" in theorem_with_sorry and "hbudget" in theorem_with_sorry:
        suggestions.append("simpa [in_budget_set] using hbudget")
    if "continuous_attains_max_on_compact" in theorem_with_sorry:
        suggestions.append("simpa using continuous_attains_max_on_compact hs hne hf")
    if "continuous_attains_min_on_compact" in theorem_with_sorry:
        suggestions.append("simpa using continuous_attains_min_on_compact hs hne hf")
    if "hx : pareto_efficient" in theorem_with_sorry or "hx : pareto_efficient".lower() in lowered:
        suggestions.append("exact hx.1")
    if re.search(r"\bfield_simp\b", theorem_with_sorry):
        suggestions.append("field_simp")

    deduped: list[str] = []
    seen: set[str] = set()
    for suggestion in suggestions:
        if suggestion in seen:
            continue
        seen.add(suggestion)
        deduped.append(suggestion)
    return deduped


async def repl_fast_path(
    repl: LeanREPLSession,
    theorem_code: str,
    *,
    max_attempts: int = 30,
    job_id: str = "repl_fast_path",
) -> dict[str, Any] | None:
    """Try deterministic tactics against one LeanInteract session."""

    report: dict[str, Any] = {
        "used": False,
        "success": False,
        "attempts": [],
        "fallback_reason": None,
        "candidate_code": None,
        "candidate_result": None,
    }

    try:
        state = repl.start_proof(theorem_code)
        report["used"] = True
        if state.is_solved:
            candidate_result = repl.verify_materialized_proof(filename=f"{job_id}_fast_0.lean")
            report["attempts"].append(
                {
                    "step": 0,
                    "mode": "repl_fast_path",
                    "tactic": "trivial",
                    "success": candidate_result["success"],
                    "proof_status": "Completed",
                    "errors": candidate_result.get("errors", []),
                }
            )
            if candidate_result["success"]:
                report["success"] = True
                report["candidate_code"] = repl.materialize_proof()
                report["candidate_result"] = candidate_result
                return report

        tactics = suggest_fast_path_tactics(theorem_code)[:max_attempts]
        for step, tactic in enumerate(tactics, start=1):
            if step > 1:
                state = repl.start_proof(theorem_code)

            response = repl.apply_tactic(state.state_id, tactic)
            if isinstance(response, LeanError):
                report["attempts"].append(
                    {
                        "step": step,
                        "mode": "repl_fast_path",
                        "tactic": tactic,
                        "success": False,
                        "proof_status": "LeanError",
                        "errors": [response.message],
                    }
                )
                continue

            errors: list[str] = []
            if response.has_errors():
                if hasattr(response, "get_errors"):
                    errors = [message.data for message in response.get_errors()]
                report["attempts"].append(
                    {
                        "step": step,
                        "mode": "repl_fast_path",
                        "tactic": tactic,
                        "success": False,
                        "proof_status": getattr(response, "proof_status", "Incomplete"),
                        "errors": errors,
                    }
                )
                continue

            proof_status = getattr(response, "proof_status", "Completed")
            report["attempts"].append(
                {
                    "step": step,
                    "mode": "repl_fast_path",
                    "tactic": tactic,
                    "success": True,
                    "proof_status": proof_status,
                    "errors": [],
                }
            )
            if proof_status != "Completed":
                continue

            candidate_result = repl.verify_materialized_proof(filename=f"{job_id}_fast_{step}.lean")
            if not candidate_result["success"]:
                report["attempts"][-1]["success"] = False
                report["attempts"][-1]["errors"] = candidate_result.get("errors", [])
                continue

            report["success"] = True
            report["candidate_code"] = repl.materialize_proof()
            report["candidate_result"] = candidate_result
            return report

        report["fallback_reason"] = "REPL session completed without closing the theorem"
    except Exception as exc:
        report["fallback_reason"] = f"{type(exc).__name__}: {exc}"

    return report
