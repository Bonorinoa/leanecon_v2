"""Local tactic shortcuts for cheap proving attempts."""

from __future__ import annotations

import re


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
