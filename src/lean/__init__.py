"""Lean integration helpers for LeanEcon v2."""

from .compiler import compile_check, compile_lean_code, lean_run_code, lean_workspace_available
from .validators import contains_sorry, detect_sorry, has_axiom_warning, validate_axioms

try:
    from .repl import LeanREPL, LeanREPLSession, ProofSessionState, TacticResult
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    LeanREPL = None  # type: ignore[assignment]
    LeanREPLSession = None  # type: ignore[assignment]
    ProofSessionState = None  # type: ignore[assignment]
    TacticResult = None  # type: ignore[assignment]

__all__ = [
    "compile_check",
    "compile_lean_code",
    "lean_run_code",
    "lean_workspace_available",
    "contains_sorry",
    "detect_sorry",
    "has_axiom_warning",
    "validate_axioms",
    "LeanREPL",
    "LeanREPLSession",
    "ProofSessionState",
    "TacticResult",
]
