"""Local tactic shortcuts for cheap proving attempts."""

from __future__ import annotations


def suggest_fast_path_tactics(theorem_with_sorry: str) -> list[str]:
    """Return deterministic tactic suggestions based on obvious patterns."""

    lowered = theorem_with_sorry.lower()
    suggestions: list[str] = []

    if " true " in f" {lowered} ":
        suggestions.append("trivial")
    if " = " in theorem_with_sorry:
        suggestions.append("rfl")
    if "∧" in theorem_with_sorry or "/\\" in theorem_with_sorry:
        suggestions.append("constructor")

    return suggestions
