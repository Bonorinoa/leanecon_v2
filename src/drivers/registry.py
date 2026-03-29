"""Driver discovery and selection helpers."""

from __future__ import annotations

from . import base as _base
from . import mistral as _mistral  # noqa: F401
from .base import DriverConfig, get_formalizer_driver, get_prover_driver

try:  # Optional dependency: benchmark and Mistral-only flows should still import cleanly.
    from . import gemini as _gemini  # noqa: F401
except ModuleNotFoundError as exc:
    if exc.name not in {"google", "google.genai"}:
        raise


def available_prover_drivers() -> list[str]:
    """Return the registered prover driver names."""

    return sorted(_base._prover_drivers.keys())


def available_formalizer_drivers() -> list[str]:
    """Return the registered formalizer driver names."""

    return sorted(_base._formalizer_drivers.keys())


__all__ = [
    "DriverConfig",
    "available_formalizer_drivers",
    "available_prover_drivers",
    "get_formalizer_driver",
    "get_prover_driver",
]
