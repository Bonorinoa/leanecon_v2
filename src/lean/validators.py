"""Validation helpers for Lean source."""

from __future__ import annotations


def contains_sorry(theorem_code: str) -> bool:
    """Return whether the theorem still contains `sorry`."""

    return "sorry" in theorem_code


def has_axiom_warning(lean_output: str) -> bool:
    """Detect axiom-related warnings in Lean output."""

    lowered = lean_output.lower()
    return "axiom" in lowered or "unsafe" in lowered
