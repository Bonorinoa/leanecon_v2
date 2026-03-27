"""Lean compiler wrapper scaffold."""

from __future__ import annotations

from src.config import COMING_SOON_MESSAGE
from src.models import CompileResponse


def compile_lean_code(lean_code: str) -> CompileResponse:
    """Return a placeholder compile response until Phase 3 lands."""

    _ = lean_code
    return CompileResponse(
        success=False,
        output=COMING_SOON_MESSAGE,
        errors=[COMING_SOON_MESSAGE],
    )
