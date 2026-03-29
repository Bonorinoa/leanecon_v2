"""Statement-shaping utilities for LeanEcon v2."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from src.config import (
    DEFAULT_DRIVER,
    FORMALIZE_TEMPERATURE,
    MAX_FORMALIZE_ATTEMPTS,
)
from src.drivers.base import FormalizerDriver
from src.drivers.provider_config import provider_driver_config
from src.drivers.registry import get_formalizer_driver
from src.formalizer.prompts import (
    build_formalize_system_prompt,
    build_formalize_user_prompt,
    build_repair_system_prompt,
    build_repair_user_prompt,
)
from src.lean import compile_check
from src.models import FormalizeResponse
from src.search import FormalizationContext, build_formalization_context
from src.store.cache import JsonCache

RAW_LEAN_MARKERS = ("theorem ", "lemma ", "example ", ":= by", "by\n", "import Mathlib")
NEEDS_DEFINITION_MARKERS = ("custom axiom", "define a new", "new notion", "introduce")
THEOREM_RE = re.compile(r"(?m)^\s*(theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_']*)\b")
IMPORT_RE = re.compile(r"(?m)^\s*import\s+([A-Za-z0-9_.]+)\s*$")

_FORMALIZATION_CACHE = JsonCache()


def scope_check(raw_claim: str) -> Literal["IN_SCOPE", "NEEDS_DEFINITIONS", "RAW_LEAN"]:
    """Classify a claim before formalization."""

    lowered = raw_claim.lower()
    if any(marker in lowered for marker in RAW_LEAN_MARKERS):
        return "RAW_LEAN"
    if any(marker in lowered for marker in NEEDS_DEFINITION_MARKERS):
        return "NEEDS_DEFINITIONS"
    return "IN_SCOPE"


def _cache_key(raw_claim: str, preamble_names: list[str]) -> str:
    digest = hashlib.sha256(
        f"{raw_claim}\0{DEFAULT_DRIVER}\0{','.join(sorted(preamble_names))}".encode("utf-8")
    ).hexdigest()
    return f"formalize:{digest}"


def _slugify_claim(raw_claim: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", raw_claim.lower())
    if not tokens:
        return "generated_claim"
    slug = "_".join(tokens[:8]).strip("_")
    if not slug or slug[0].isdigit():
        slug = f"claim_{slug}"
    return slug[:64]


def _strip_fences(raw_output: str) -> str:
    lines = raw_output.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _selected_imports(context: FormalizationContext) -> list[str]:
    imports = ["Mathlib"]
    for import_name in context.preamble_imports:
        imports.append(import_name)
    seen: set[str] = set()
    ordered: list[str] = []
    for import_name in imports:
        if import_name in seen:
            continue
        seen.add(import_name)
        ordered.append(import_name)
    return ordered


def _ensure_imports(theorem_code: str, context: FormalizationContext) -> str:
    existing_imports = IMPORT_RE.findall(theorem_code)
    body_lines = [
        line for line in theorem_code.splitlines() if not line.strip().startswith("import ")
    ]
    imports = _selected_imports(context)
    merged_imports = []
    seen: set[str] = set()
    for import_name in imports + existing_imports:
        if import_name in seen:
            continue
        seen.add(import_name)
        merged_imports.append(f"import {import_name}")
    return "\n".join(merged_imports) + "\n\n" + "\n".join(body_lines).strip() + "\n"


def _rewrite_decl_name(lean_code: str, theorem_name: str) -> str:
    match = THEOREM_RE.search(lean_code)
    if match is None:
        return lean_code
    start, end = match.span(2)
    return lean_code[:start] + theorem_name + lean_code[end:]


def _first_matching_preamble(context: FormalizationContext) -> str | None:
    return context.preamble_names[0] if context.preamble_names else None


def _heuristic_template(raw_claim: str, context: FormalizationContext) -> str:
    theorem_name = _slugify_claim(raw_claim)
    imports = "\n".join(f"import {name}" for name in _selected_imports(context))
    entry_name = _first_matching_preamble(context)
    lowered = raw_claim.lower()

    if entry_name == "budget_set":
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (p₁ p₂ m x₁ x₂ : ℝ)
    (hbudget : p₁ * x₁ + p₂ * x₂ ≤ m) :
    in_budget_set p₁ p₂ m x₁ x₂ := by
  sorry
"""

    if entry_name == "extreme_value_theorem" and "minimum" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    {{α : Type*}} [TopologicalSpace α]
    {{s : Set α}} {{f : α → ℝ}}
    (hs : IsCompact s) (hne : s.Nonempty)
    (hf : ContinuousOn f s) :
    ∃ x ∈ s, IsMinOn f s x := by
  sorry
"""

    if entry_name == "extreme_value_theorem":
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    {{α : Type*}} [TopologicalSpace α]
    {{s : Set α}} {{f : α → ℝ}}
    (hs : IsCompact s) (hne : s.Nonempty)
    (hf : ContinuousOn f s) :
    ∃ x ∈ s, IsMaxOn f s x := by
  sorry
"""

    if entry_name == "crra_utility":
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (c γ : ℝ) (hc : c > 0) (_ : γ > 0) (_ : γ ≠ 1) :
    -c * (-γ * c⁻¹) = γ := by
  sorry
"""

    if entry_name == "cobb_douglas_2factor":
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (α K : ℝ) (_ : 0 < α) (_ : α < 1) (hK : K > 0) :
    α * K * K⁻¹ = α := by
  sorry
"""

    if entry_name == "pareto_efficiency":
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    {{n : ℕ}} {{X : Type*}}
    (u : Fin n → X → ℝ) (feasible : Set X) (x : X)
    (hx : pareto_efficient u feasible x) :
    x ∈ feasible := by
  sorry
"""

    return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (claim : Prop) :
    claim := by
  sorry
"""


def _classify_repair_bucket(errors: list[str]) -> str:
    lowered = "\n".join(errors).lower()
    if "unknown module prefix" in lowered or "bad import" in lowered:
        return "unknown_import_module"
    if "unknown constant" in lowered or "unknown identifier" in lowered:
        return "unknown_identifier"
    if "failed to synthesize" in lowered:
        return "typeclass_instance"
    if "expected" in lowered or "invalid syntax" in lowered:
        return "syntax_notation"
    return "semantic_mismatch"


def _repair_candidate(raw_claim: str, theorem_code: str, context: FormalizationContext) -> str:
    if THEOREM_RE.search(theorem_code) is None or "sorry" not in theorem_code:
        return _heuristic_template(raw_claim, context)

    repaired = _ensure_imports(_strip_fences(theorem_code), context)
    if ":= by" not in repaired:
        repaired = repaired.rstrip() + "\n:= by\n  sorry\n"
    return repaired


def _provider_driver() -> FormalizerDriver | None:
    config = provider_driver_config(
        driver_name=DEFAULT_DRIVER,
        temperature=FORMALIZE_TEMPERATURE,
    )
    if not config.api_key:
        return None
    return get_formalizer_driver(DEFAULT_DRIVER, config)


def _compile_errors(compile_result: dict[str, Any]) -> list[str]:
    """Extract a stable list of diagnostics from one compile result."""

    errors = list(compile_result.get("errors") or [])
    if errors:
        return errors
    output = str(compile_result.get("output", "")).strip()
    return [output] if output else ["Lean compilation failed without diagnostics."]


def _dedupe_errors(errors: list[str]) -> list[str]:
    """Keep error reporting compact and stable for API responses."""

    seen: set[str] = set()
    deduped: list[str] = []
    for error in errors:
        if error in seen:
            continue
        seen.add(error)
        deduped.append(error)
    return deduped


async def _provider_attempt(raw_claim: str, context: FormalizationContext) -> str | None:
    driver = _provider_driver()
    if driver is None:
        return None

    try:
        raw_output = await driver.formalize(
            system_prompt=build_formalize_system_prompt(
                context_block=context.build_prompt_block(),
                preamble_block=context.preamble_block,
            ),
            user_prompt=build_formalize_user_prompt(raw_claim),
        )
    except RuntimeError:
        return None
    return _repair_candidate(raw_claim, raw_output, context)


async def _provider_repair_attempt(
    raw_claim: str,
    theorem_code: str,
    context: FormalizationContext,
    errors: list[str],
) -> str | None:
    """Ask the provider for one bounded repair pass after compilation failure."""

    driver = _provider_driver()
    if driver is None:
        return None

    bucket = _classify_repair_bucket(errors)
    try:
        raw_output = await driver.formalize(
            system_prompt=build_repair_system_prompt(
                bucket,
                context_block=context.build_prompt_block(),
                preamble_block=context.preamble_block,
            ),
            user_prompt=build_repair_user_prompt(raw_claim, theorem_code, errors),
        )
    except RuntimeError:
        return None
    return _repair_candidate(raw_claim, raw_output, context)


async def formalize_claim(
    raw_claim: str,
    preamble_names: list[str] | None = None,
    search_context: dict[str, Any] | None = None,
) -> FormalizeResponse:
    """Generate a compile-validated Lean theorem stub."""

    scope = scope_check(raw_claim)
    if scope == "NEEDS_DEFINITIONS":
        return FormalizeResponse(
            success=False,
            theorem_code=None,
            scope=scope,
            search_context=search_context or {},
            attempts=0,
            errors=["Claim appears to require new definitions before formalization."],
            message="Needs additional theory or definitions.",
        )

    context = build_formalization_context(raw_claim, preamble_names)
    context_payload = search_context or context.to_search_context()
    cache_key = _cache_key(raw_claim, context.preamble_names)
    cached = _FORMALIZATION_CACHE.get(cache_key)
    if cached:
        return FormalizeResponse.model_validate(cached)

    if scope == "RAW_LEAN":
        normalized = _repair_candidate(raw_claim, raw_claim, context)
        compile_result = compile_check(normalized)
        errors = list(compile_result["errors"])
        success = not errors and compile_result["has_sorry"]
        response = FormalizeResponse(
            success=success,
            theorem_code=normalized if success else None,
            scope=scope,
            search_context=context_payload,
            attempts=1,
            errors=errors,
            message=(
                "Accepted raw Lean theorem stub."
                if success
                else "Raw Lean input did not compile cleanly."
            ),
        )
        if success:
            _FORMALIZATION_CACHE.set(cache_key, response.model_dump())
        return response

    attempts = 0
    collected_errors: list[str] = []
    candidate = _heuristic_template(raw_claim, context)
    provider_candidate = await _provider_attempt(raw_claim, context)
    if provider_candidate:
        candidate = provider_candidate

    while attempts < MAX_FORMALIZE_ATTEMPTS:
        attempts += 1
        compile_result = compile_check(candidate)
        if compile_result["has_sorry"] and not compile_result["errors"]:
            response = FormalizeResponse(
                success=True,
                theorem_code=candidate,
                scope=scope,
                search_context=context_payload,
                attempts=attempts,
                errors=_dedupe_errors(collected_errors),
                message="Generated a Lean theorem stub that compiles with `sorry`.",
            )
            _FORMALIZATION_CACHE.set(cache_key, response.model_dump())
            return response

        current_errors = _compile_errors(compile_result)
        collected_errors.extend(current_errors)
        repaired_candidate = _repair_candidate(raw_claim, candidate, context)
        if repaired_candidate != candidate:
            candidate = repaired_candidate
            continue

        provider_repair = await _provider_repair_attempt(
            raw_claim,
            candidate,
            context,
            current_errors,
        )
        if provider_repair and provider_repair != candidate:
            candidate = provider_repair
            continue

        if _classify_repair_bucket(current_errors) == "semantic_mismatch":
            candidate = _heuristic_template(raw_claim, context)
            continue

    return FormalizeResponse(
        success=False,
        theorem_code=None,
        scope=scope,
        search_context=context_payload,
        attempts=attempts,
        errors=_dedupe_errors(collected_errors)[:10],
        message="Unable to produce a compile-valid theorem stub.",
    )
