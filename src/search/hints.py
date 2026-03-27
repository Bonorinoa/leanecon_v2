"""Curated deterministic hint definitions for retrieval and formalization."""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")


@dataclass(frozen=True)
class HintDefinition:
    """Static hint bundle used by deterministic retrieval."""

    name: str
    description: str
    keywords: tuple[str, ...]
    candidate_imports: tuple[str, ...]
    candidate_identifiers: tuple[str, ...]
    domain: str = "economics"


CURATED_HINTS: tuple[HintDefinition, ...] = (
    HintDefinition(
        name="pareto-welfare",
        description="Welfare claims often reduce to Pareto dominance or Pareto efficiency.",
        keywords=("pareto", "efficient", "optimal", "welfare"),
        candidate_imports=("LeanEcon.Preamble.Welfare.ParetoEfficiency",),
        candidate_identifiers=("pareto_dominates", "pareto_efficient"),
    ),
    HintDefinition(
        name="utility-optimization",
        description="Consumer-theory claims often need utility definitions or compactness tools.",
        keywords=("utility", "optimization", "maximize", "maximizes", "argmax", "consumer"),
        candidate_imports=(
            "LeanEcon.Preamble.Consumer.CRRAUtility",
            "LeanEcon.Preamble.Consumer.CARAUtility",
            "Mathlib.Topology.Order.Basic",
        ),
        candidate_identifiers=("crra_utility", "ContinuousOn", "IsMaxOn"),
    ),
    HintDefinition(
        name="extreme-value",
        description=(
            "Existence and optimization claims often use compactness "
            "and extreme-value lemmas."
        ),
        keywords=("exists", "existence", "compact", "continuous", "maximum", "minimum"),
        candidate_imports=(
            "LeanEcon.Preamble.Optimization.ExtremeValueTheorem",
            "Mathlib.Topology.Order.Basic",
        ),
        candidate_identifiers=(
            "continuous_attains_max_on_compact",
            "continuous_attains_min_on_compact",
            "IsCompact.exists_isMaxOn",
        ),
    ),
    HintDefinition(
        name="game-theory",
        description=(
            "Strategic interaction claims often need Nash-style definitions and "
            "best responses."
        ),
        keywords=("game", "strategy", "nash", "best", "response"),
        candidate_imports=("LeanEcon.Preamble.GameTheory.ExpectedPayoff",),
        candidate_identifiers=("expected_payoff_2x2",),
        domain="game_theory",
    ),
    HintDefinition(
        name="budget-set",
        description=(
            "Budget-constraint claims often benefit from the reusable "
            "budget-set predicate."
        ),
        keywords=("budget", "constraint", "bundle", "income", "spending"),
        candidate_imports=("LeanEcon.Preamble.Consumer.BudgetSet",),
        candidate_identifiers=("in_budget_set",),
    ),
    HintDefinition(
        name="production",
        description="Production claims may align with Cobb-Douglas or CES preamble modules.",
        keywords=("production", "cobb-douglas", "ces", "elasticity", "firm"),
        candidate_imports=(
            "LeanEcon.Preamble.Producer.CobbDouglas2Factor",
            "LeanEcon.Preamble.Producer.CES2Factor",
        ),
        candidate_identifiers=("cobb_douglas", "cobb_douglas_elasticity_capital"),
    ),
)


def match_curated_hints(raw_claim: str, domain: str) -> list[HintDefinition]:
    """Return deterministic curated hints ranked by lexical overlap."""

    tokens = set(TOKEN_RE.findall(raw_claim.lower()))
    scored_hints: list[tuple[int, HintDefinition]] = []
    allowed_domains = {domain}
    if domain != "economics":
        allowed_domains.add("economics")

    for hint in CURATED_HINTS:
        if hint.domain not in allowed_domains:
            continue

        overlap = tokens.intersection(hint.keywords)
        if overlap:
            scored_hints.append((len(overlap), hint))

    scored_hints.sort(key=lambda item: (-item[0], item[1].name))
    return [hint for _, hint in scored_hints]
