"""Deterministic search engine for LeanEcon v2."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from src.config import LEAN_PROOF_DIR, LEAN_WORKSPACE, PREAMBLE_DIR, PROJECT_ROOT
from src.models import CuratedHint, PreambleMatch, SearchResponse
from src.search.hints import HintDefinition, match_curated_hints

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")
DECLARATION_RE = re.compile(
    r"^\s*(?:theorem|lemma|def|structure|class|axiom)\s+([A-Za-z0-9_'.]+)",
    re.MULTILINE,
)

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "game_theory": ("game", "strategy", "nash", "auction"),
    "finance": ("asset", "pricing", "bond", "portfolio"),
    "economics": ("equilibrium", "utility", "market", "consumer", "producer"),
}


def _normalize_claim(raw_claim: str) -> str:
    """Normalize user input into a whitespace-stable token stream."""

    tokens = TOKEN_RE.findall(raw_claim.lower())
    return " ".join(tokens)


def _tokenize(text: str) -> set[str]:
    """Tokenize user input or file content for lexical matching."""

    return set(TOKEN_RE.findall(text.lower()))


def _resolve_domain(requested_domain: str, normalized_claim: str) -> str:
    """Use the requested domain unless it is blank, otherwise infer a best effort tag."""

    if requested_domain.strip():
        return requested_domain.strip().lower()

    claim_tokens = _tokenize(normalized_claim)
    best_domain = "economics"
    best_score = 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = len(claim_tokens.intersection(keywords))
        if score > best_score:
            best_domain = domain
            best_score = score
    return best_domain


def _iter_candidate_files() -> Iterable[Path]:
    """Yield candidate Lean files from the preamble or proof workspace."""

    if PREAMBLE_DIR.exists():
        yield from sorted(PREAMBLE_DIR.rglob("*.lean"))
        return

    if LEAN_PROOF_DIR.exists():
        yield from sorted(LEAN_PROOF_DIR.rglob("*.lean"))


def _relative_path(path: Path) -> str:
    """Return a stable project-relative path string."""

    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _import_path(path: Path) -> str:
    """Convert a Lean source file into a Lean import path."""

    try:
        relative = path.relative_to(LEAN_WORKSPACE).with_suffix("")
    except ValueError:
        relative = path.with_suffix("")
    return ".".join(relative.parts)


def _extract_identifiers(contents: str) -> list[str]:
    """Extract a small deterministic set of declaration identifiers from Lean source."""

    identifiers = [match.group(1) for match in DECLARATION_RE.finditer(contents)]
    return identifiers[:10]


def _match_files(claim_tokens: set[str]) -> tuple[list[PreambleMatch], set[str], set[str]]:
    """Match local Lean files and return response models plus advisory symbols."""

    matches: list[PreambleMatch] = []
    candidate_imports: set[str] = set()
    candidate_identifiers: set[str] = set()

    for path in _iter_candidate_files():
        contents = path.read_text(encoding="utf-8", errors="ignore")
        name_tokens = _tokenize(path.stem.replace("_", " "))
        content_tokens = _tokenize(contents)
        overlap = claim_tokens.intersection(name_tokens.union(content_tokens))
        if not overlap:
            continue

        import_path = _import_path(path)
        candidate_imports.add(import_path)
        identifiers = _extract_identifiers(contents)
        candidate_identifiers.update(identifiers)
        matches.append(
            PreambleMatch(
                name=path.stem,
                path=_relative_path(path),
                score=float(len(overlap)),
                reason=f"Matched lexical overlap on: {', '.join(sorted(overlap)[:5])}",
            )
        )

    matches.sort(key=lambda item: (-item.score, item.name))
    return matches[:5], candidate_imports, candidate_identifiers


def _build_hint_models(
    hints: Iterable[HintDefinition], claim_tokens: set[str]
) -> list[CuratedHint]:
    """Convert static hint definitions into API response models."""

    models: list[CuratedHint] = []
    for hint in hints:
        overlap = sorted(claim_tokens.intersection(hint.keywords))
        models.append(
            CuratedHint(
                name=hint.name,
                description=hint.description,
                keywords=overlap,
                candidate_imports=list(hint.candidate_imports),
                candidate_identifiers=list(hint.candidate_identifiers),
            )
        )
    return models


def search_claim(raw_claim: str, domain: str = "economics") -> SearchResponse:
    """Run deterministic retrieval for a raw claim."""

    normalized_claim = _normalize_claim(raw_claim)
    claim_tokens = _tokenize(normalized_claim)
    resolved_domain = _resolve_domain(domain, normalized_claim)

    hints = match_curated_hints(normalized_claim, resolved_domain)
    hint_models = _build_hint_models(hints, claim_tokens)
    preamble_matches, file_imports, file_identifiers = _match_files(claim_tokens)

    candidate_imports = sorted(
        file_imports.union(
            import_name
            for hint in hint_models
            for import_name in hint.candidate_imports
        )
    )
    candidate_identifiers = sorted(
        file_identifiers.union(
            identifier
            for hint in hint_models
            for identifier in hint.candidate_identifiers
        )
    )

    return SearchResponse(
        preamble_matches=preamble_matches,
        curated_hints=hint_models,
        domain=resolved_domain,
        candidate_imports=candidate_imports,
        candidate_identifiers=candidate_identifiers,
    )
