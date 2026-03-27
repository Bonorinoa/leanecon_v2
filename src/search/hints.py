"""Curated deterministic hint definitions for Phase 2A retrieval."""

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
        name="competitive-equilibrium",
        description="Claims about equilibrium often depend on market clearing and Pareto tools.",
        keywords=("equilibrium", "competitive", "walrasian", "market"),
        candidate_imports=("LeanEcon.Preamble.Equilibrium",),
        candidate_identifiers=("CompetitiveEquilibrium", "marketClearing", "paretoOptimal"),
    ),
    HintDefinition(
        name="utility-optimization",
        description="Optimization claims usually need utility, preference, or argmax-style lemmas.",
        keywords=("utility", "optimization", "maximize", "maximizes", "argmax"),
        candidate_imports=("LeanEcon.Preamble.Optimization",),
        candidate_identifiers=("Utility", "argmax", "isOptimal"),
    ),
    HintDefinition(
        name="fixed-point-existence",
        description="Existence claims may benefit from fixed-point or compactness-related imports.",
        keywords=("exists", "existence", "fixed", "compact", "continuous"),
        candidate_imports=("LeanEcon.Preamble.Existence",),
        candidate_identifiers=("exists_equilibrium", "FixedPoint", "compactSpace"),
    ),
    HintDefinition(
        name="game-theory",
        description=(
            "Strategic interaction claims often need Nash-style definitions and "
            "best responses."
        ),
        keywords=("game", "strategy", "nash", "best", "response"),
        candidate_imports=("LeanEcon.Preamble.GameTheory",),
        candidate_identifiers=("NashEquilibrium", "bestResponse", "mixedStrategy"),
        domain="game_theory",
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
