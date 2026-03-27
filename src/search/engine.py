"""Deterministic search engine for LeanEcon v2."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import LEAN_PROOF_DIR, LEAN_WORKSPACE, PREAMBLE_DIR, PROJECT_ROOT
from src.models import CuratedHint, PreambleMatch, SearchResponse
from src.preamble_library import (
    PreambleEntry,
    build_preamble_block,
    build_preamble_imports,
    get_preamble_entries,
    rank_matching_preambles,
)
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

MAX_AUTO_PREAMBLES = 2


@dataclass
class FormalizationContext:
    """Structured advisory retrieval context for theorem-stub generation."""

    claim_text: str
    search_response: SearchResponse
    explicit_preamble_names: list[str] = field(default_factory=list)
    auto_preamble_names: list[str] = field(default_factory=list)
    preamble_names: list[str] = field(default_factory=list)
    preamble_block: str = ""
    preamble_imports: list[str] = field(default_factory=list)
    candidate_imports: list[str] = field(default_factory=list)
    candidate_identifiers: list[str] = field(default_factory=list)
    retrieval_notes: list[str] = field(default_factory=list)

    def build_prompt_block(self) -> str:
        """Render a compact prompt-friendly summary."""

        lines = ["RETRIEVAL CONTEXT (advisory):"]
        if self.search_response.domain:
            lines.append(f"- Domain: {self.search_response.domain}")
        if self.preamble_names:
            lines.append(f"- Matching preambles: {', '.join(self.preamble_names)}")
        if self.candidate_imports:
            lines.append(f"- Candidate imports: {', '.join(self.candidate_imports[:8])}")
        if self.candidate_identifiers:
            lines.append(
                f"- Candidate identifiers: {', '.join(self.candidate_identifiers[:12])}"
            )
        if self.retrieval_notes:
            lines.append(f"- Notes: {' | '.join(self.retrieval_notes[:6])}")
        return "\n".join(lines)

    def to_search_context(self) -> dict[str, Any]:
        """Return a JSON-serializable retrieval summary for API responses."""

        return {
            "domain": self.search_response.domain,
            "preamble_matches": [
                match.model_dump() for match in self.search_response.preamble_matches
            ],
            "curated_hints": [hint.model_dump() for hint in self.search_response.curated_hints],
            "explicit_preambles": list(self.explicit_preamble_names),
            "auto_preambles": list(self.auto_preamble_names),
            "preamble_names": list(self.preamble_names),
            "candidate_imports": list(self.candidate_imports),
            "candidate_identifiers": list(self.candidate_identifiers),
            "notes": list(self.retrieval_notes),
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


def _match_preamble_entries(raw_claim: str) -> tuple[list[PreambleMatch], set[str], set[str]]:
    """Match claims against the curated preamble library metadata."""

    matches: list[PreambleMatch] = []
    candidate_imports: set[str] = set()
    candidate_identifiers: set[str] = set()

    for entry, score in rank_matching_preambles(raw_claim):
        candidate_imports.add(entry.lean_module)
        path = entry.lean_path
        if path.exists():
            contents = path.read_text(encoding="utf-8", errors="ignore")
            candidate_identifiers.update(_extract_identifiers(contents))
        matches.append(
            PreambleMatch(
                name=entry.name,
                path=_relative_path(path),
                score=float(score),
                reason=f"Matched preamble keywords for {entry.description}",
            )
        )

    return matches, candidate_imports, candidate_identifiers


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
    entry_matches, entry_imports, entry_identifiers = _match_preamble_entries(raw_claim)
    file_matches, file_imports, file_identifiers = _match_files(claim_tokens)

    seen_match_names: set[str] = set()
    preamble_matches: list[PreambleMatch] = []
    for match in sorted(
        entry_matches + file_matches,
        key=lambda item: (-item.score, item.name),
    ):
        dedupe_key = f"{match.name}:{match.path}"
        if dedupe_key in seen_match_names:
            continue
        seen_match_names.add(dedupe_key)
        preamble_matches.append(match)
        if len(preamble_matches) >= 5:
            break

    candidate_imports = sorted(
        entry_imports.union(file_imports).union(
            import_name
            for hint in hint_models
            for import_name in hint.candidate_imports
        )
    )
    candidate_identifiers = sorted(
        entry_identifiers.union(file_identifiers).union(
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


def build_formalization_context(
    raw_claim: str,
    explicit_preamble_names: list[str] | None = None,
) -> FormalizationContext:
    """Build bounded retrieval context for the formalizer."""

    explicit_entries = get_preamble_entries(explicit_preamble_names or [])
    explicit_names = [entry.name for entry in explicit_entries]

    auto_names: list[str] = []
    if not explicit_names:
        auto_names = [
            entry.name
            for entry, _score in rank_matching_preambles(raw_claim, auto=True)[
                :MAX_AUTO_PREAMBLES
            ]
        ]

    selected_entries: list[PreambleEntry] = explicit_entries or get_preamble_entries(auto_names)
    search_response = search_claim(raw_claim)
    preamble_imports = build_preamble_imports(selected_entries)
    candidate_imports = sorted(
        set(search_response.candidate_imports).union(
            entry.lean_module for entry in selected_entries
        )
    )
    candidate_identifiers = list(search_response.candidate_identifiers)
    retrieval_notes = [hint.description for hint in search_response.curated_hints]
    if explicit_names:
        retrieval_notes.insert(0, "Caller supplied explicit preamble names.")
    elif auto_names:
        retrieval_notes.insert(0, "Auto-selected preambles from deterministic keyword matching.")

    return FormalizationContext(
        claim_text=raw_claim,
        search_response=search_response,
        explicit_preamble_names=explicit_names,
        auto_preamble_names=[] if explicit_names else auto_names,
        preamble_names=[entry.name for entry in selected_entries],
        preamble_block=build_preamble_block(selected_entries),
        preamble_imports=preamble_imports,
        candidate_imports=candidate_imports,
        candidate_identifiers=candidate_identifiers,
        retrieval_notes=retrieval_notes,
    )
