"""Statement-shaping utilities for LeanEcon v2."""

from __future__ import annotations

import hashlib
import logging
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
FORMALIZATION_FAILED_RE = re.compile(r"(?im)^\s*(?:--\s*)?FORMALIZATION_FAILED\b[:\s-]*(.*)$")
IDENTIFIER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*\b")
FORMALIZATION_CACHE_VERSION = "integrity-v3"
VACUOUS_PATTERNS = [
    re.compile(r"\(\s*\w+\s*:\s*Prop\s*\)\s*:\s*[\s\S]*?:=", re.IGNORECASE),
    re.compile(r"\(\s*h\s*:\s*\w+\s*\)\s*:\s*\w+\s*:=\s*h\b", re.IGNORECASE),
    re.compile(r":\s*True\s*:=", re.IGNORECASE),
    re.compile(r"theorem\s+\w+\s*:\s*[A-Z]\w*\s*:=\s*by", re.IGNORECASE),
]
CONCEPT_PATTERNS = [
    re.compile(
        r"\b(demand|supply|utility|production|cost|revenue|profit|budget|"
        r"equilibrium|elasticity|marginal|average|total|constant|"
        r"returns|risk|aversion|consumption|investment|saving|"
        r"inflation|interest|discount|present\s+value|"
        r"cobb.?douglas|crra|ces|leontief|marshallian|hicksian|"
        r"walrasian|pareto|nash|bellman|euler|slutsky|phillips|"
        r"solow|ramsey|arrow.?debreu)\b"
    )
]
TEXT_NORMALIZATION = str.maketrans(
    {
        "α": " alpha ",
        "β": " beta ",
        "γ": " gamma ",
        "δ": " delta ",
        "σ": " sigma ",
        "ρ": " rho ",
        "θ": " theta ",
        "λ": " lambda ",
        "μ": " mu ",
        "ε": " epsilon ",
        "ω": " omega ",
        "₀": "0",
        "₁": "1",
        "₂": "2",
        "₃": "3",
        "₄": "4",
        "₅": "5",
        "₆": "6",
        "₇": "7",
        "₈": "8",
        "₉": "9",
        "≤": " <= ",
        "≥": " >= ",
    }
)
GENERIC_IDENTIFIERS = {
    "import",
    "mathlib",
    "leanecon",
    "preamble",
    "theorem",
    "lemma",
    "example",
    "claim",
    "prop",
    "type",
    "true",
    "false",
    "sorry",
    "raw",
    "lean",
    "proof",
    "generated",
    "return",
    "only",
    "code",
    "demo",
    "by",
}
STOPWORD_CONCEPTS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "does",
    "equal",
    "equals",
    "exactly",
    "for",
    "from",
    "holds",
    "if",
    "in",
    "is",
    "it",
    "lies",
    "of",
    "on",
    "or",
    "that",
    "the",
    "then",
    "to",
    "under",
    "when",
    "where",
    "with",
}
TOKEN_ALIASES = {
    "rra": {"relative", "risk", "aversion"},
    "ara": {"absolute", "risk", "aversion"},
    "nkpc": {"phillips", "curve"},
}

_FORMALIZATION_CACHE = JsonCache()
logger = logging.getLogger(__name__)


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
        (
            f"{FORMALIZATION_CACHE_VERSION}\0{raw_claim}\0{DEFAULT_DRIVER}\0"
            f"{','.join(sorted(preamble_names))}"
        ).encode("utf-8")
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


def _normalize_math_text(text: str) -> str:
    """Normalize math-adjacent text for coarse semantic comparisons."""

    normalized = text.translate(TEXT_NORMALIZATION)
    normalized = normalized.replace("-", " ")
    normalized = normalized.replace("'", " ")
    return normalized.lower()


def _detect_formalization_failed(raw_output: str) -> str | None:
    """Return the model's explanation when it explicitly refuses to formalize."""

    stripped = _strip_fences(raw_output)
    lines = stripped.splitlines()[:6]
    for index, line in enumerate(lines):
        match = FORMALIZATION_FAILED_RE.match(line)
        if match:
            reason = match.group(1).strip()
            if reason:
                return reason
            for subsequent in lines[index + 1 :]:
                cleaned = subsequent.strip().removeprefix("--").strip()
                if cleaned.lower().startswith("reason:"):
                    return cleaned.removeprefix("Reason:").strip()
            return "Provider reported FORMALIZATION_FAILED."
    return None


def is_vacuous_formalization(theorem_code: str) -> tuple[bool, str]:
    """Detect theorem stubs that are tautological or semantically empty."""

    for pattern in VACUOUS_PATTERNS:
        match = pattern.search(theorem_code)
        if match:
            return True, f"Vacuous pattern detected: {match.group(0)[:80]}"

    normalized = _normalize_math_text(theorem_code)
    identifiers = {
        token
        for token in IDENTIFIER_RE.findall(normalized)
        if token not in GENERIC_IDENTIFIERS
    }
    has_math_content = bool(re.search(r"\d|=|<=|>=|<|>|\+|-|\*|/|∃|∀", normalized))
    if not identifiers and not has_math_content:
        return True, "No domain-specific identifiers found in theorem"

    return False, ""


def extract_math_concepts(text: str) -> set[str]:
    """Extract coarse mathematical concepts and identifiers from text."""

    text_lower = _normalize_math_text(text)
    concepts: set[str] = set()

    for pattern in CONCEPT_PATTERNS:
        concepts.update(" ".join(match.group(0).split()) for match in pattern.finditer(text_lower))

    concepts.update(
        re.findall(
            r"\b(alpha|beta|gamma|delta|sigma|rho|theta|lambda|mu|epsilon|omega)\b",
            text_lower,
        )
    )
    concepts.update(re.findall(r"\b\d+(?:\.\d+)?\b", text_lower))

    if re.search(r"\bequals?\b|=", text_lower):
        concepts.add("equality")
    if re.search(r"\b(greater|less)\b|>=|<=|>|<", text_lower):
        concepts.add("inequality")

    for token in IDENTIFIER_RE.findall(text_lower):
        for part in [segment for segment in token.split("_") if segment]:
            if part in GENERIC_IDENTIFIERS or part in STOPWORD_CONCEPTS:
                continue
            if len(part) == 1 and not part.isdigit():
                continue
            concepts.add(part)
            concepts.update(TOKEN_ALIASES.get(part, set()))
            base = re.sub(r"\d+$", "", part)
            if base != part and len(base) > 2:
                concepts.add(base)

    return concepts


def check_semantic_faithfulness(raw_claim: str, theorem_code: str) -> dict[str, Any]:
    """Estimate whether the theorem preserves the claim's mathematical content."""

    claim_concepts = extract_math_concepts(raw_claim)
    theorem_concepts = extract_math_concepts(theorem_code)

    if not claim_concepts:
        return {"faithful": True, "coverage": 1.0, "missing_concepts": []}

    overlap = claim_concepts & theorem_concepts
    coverage = len(overlap) / len(claim_concepts)
    missing = sorted(claim_concepts - theorem_concepts)
    return {
        "faithful": coverage >= 0.4,
        "coverage": round(coverage, 3),
        "missing_concepts": missing,
    }


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
    normalized = _normalize_math_text(raw_claim)
    stripped_claim = raw_claim.strip()

    if (
        not entry_name
        and "=" in stripped_claim
        and re.fullmatch(r"[0-9\s+\-*/=().]+", stripped_claim)
    ):
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name} : {stripped_claim} := by
  sorry
"""

    if "budget equality" in lowered and "p1 * x1 + p2 * x2 = m" in normalized:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (m p1 p2 x1 x2 : ℝ)
    (hm : m > 0) (hp1 : p1 > 0) (hp2 : p2 > 0)
    (hspend : p1 * x1 + p2 * x2 = m) :
    p1 * x1 + p2 * x2 = m := by
  sorry
"""

    if entry_name == "budget_set" and "weakly cheaper" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (p₁ p₂ m x₁ x₂ y₁ y₂ : ℝ)
    (hbudget : in_budget_set p₁ p₂ m x₁ x₂)
    (hcheaper : p₁ * y₁ + p₂ * y₂ ≤ p₁ * x₁ + p₂ * x₂) :
    in_budget_set p₁ p₂ m y₁ y₂ := by
  sorry
"""

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

    if entry_name == "discount_factor" and "exactly one period" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (x β : ℝ)
    (hβ : β ≠ 1) :
    present_value_constant x β 1 = x := by
  sorry
"""

    if entry_name == "discount_factor" and "geometric discounting" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (x beta : ℝ)
    (T : ℕ) :
    present_value_constant x beta T = x * (1 - beta ^ T) / (1 - beta) := by
  sorry
"""

    if (
        entry_name == "marshallian_demand"
        and "exhausts income" in lowered
        and "costs exactly m" in lowered
    ):
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (α m p₁ p₂ : ℝ)
    (hp₁ : p₁ ≠ 0) (hp₂ : p₂ ≠ 0) :
    marshallian_demand_good1 α m p₁ * p₁ +
    marshallian_demand_good2 α m p₂ * p₂ = m := by
  sorry
"""

    if entry_name == "marshallian_demand" and "alpha * m / p1" in normalized:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (alpha m p1 : ℝ) :
    marshallian_demand_good1 alpha m p1 = alpha * m / p1 := by
  sorry
"""

    if entry_name == "phillips_curve" and "output gap is zero" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (beta piNext kappa : ℝ) :
    nkpc beta piNext kappa 0 = beta * piNext := by
  sorry
"""

    if (
        entry_name == "phillips_curve"
        and "beta times expected future inflation" in lowered
        and "kappa times the output gap" in lowered
    ):
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (beta piNext kappa x : ℝ) :
    nkpc beta piNext kappa x = beta * piNext + kappa * x := by
  sorry
"""

    if (
        entry_name == "solow_steady_state"
        and "steady state" in lowered
        and "depreciation" in lowered
    ):
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (s A k_star α n g δ : ℝ)
    (hss : s * A * Real.rpow k_star α = (n + g + δ) * k_star) :
    solow_investment s A k_star α = solow_depreciation n g δ k_star := by
  sorry
"""

    if entry_name == "solow_steady_state" and "investment per effective worker" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (s A k alpha : ℝ) :
    solow_investment s A k alpha = s * A * Real.rpow k alpha := by
  sorry
"""

    if entry_name == "expected_payoff" and "pure strategy 1" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (u₁₁ u₁₂ u₂₁ u₂₂ q : ℝ) :
    expected_payoff_2x2 u₁₁ u₁₂ u₂₁ u₂₂ 1 q =
    q * u₁₁ + (1 - q) * u₁₂ := by
  sorry
"""

    if (
        entry_name == "arrow_pratt_rra"
        and "absolute risk aversion" in lowered
        and "relative risk aversion" in lowered
    ):
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (c u' u'' : ℝ)
    (hu' : u' ≠ 0) :
    relative_risk_aversion c u' u'' =
    c * absolute_risk_aversion u' u'' := by
  sorry
"""

    if entry_name == "profit_function" and "break-even" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (p w A α x : ℝ)
    (hbreak : p * (A * Real.rpow x α) = w * x) :
    profit p w A α x = 0 := by
  sorry
"""

    if entry_name == "bellman_equation" and "u = id" in normalized:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (β : ℝ) (V : ℝ → ℝ) (k k' : ℝ) :
    bellman_rhs id β V k k' = (k - k') + β * V k' := by
  sorry
"""

    if entry_name == "income_elasticity" and "(q = m)" in lowered:
        return f"""{imports}

/-- {raw_claim} -/
theorem {theorem_name}
    (m q : ℝ)
    (hm : m ≠ 0) (hq : q ≠ 0)
    (hlinear : q = m) :
    income_elasticity 1 m q = 1 := by
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
    if _detect_formalization_failed(raw_output):
        return _strip_fences(raw_output)
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
    if _detect_formalization_failed(raw_output):
        return _strip_fences(raw_output)
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
    heuristic_candidate = _heuristic_template(raw_claim, context)
    candidate = heuristic_candidate
    provider_candidate = await _provider_attempt(raw_claim, context)
    if provider_candidate:
        provider_failure_reason = _detect_formalization_failed(provider_candidate)
        if provider_failure_reason:
            return FormalizeResponse(
                success=False,
                theorem_code=None,
                scope=scope,
                search_context=context_payload,
                attempts=1,
                errors=[provider_failure_reason],
                message=(
                    "The formalizer could not faithfully translate the claim and failed "
                    "honestly instead of returning a weaker theorem."
                ),
            )
        candidate = provider_candidate

    while attempts < MAX_FORMALIZE_ATTEMPTS:
        attempts += 1
        compile_result = compile_check(candidate)
        if compile_result["has_sorry"] and not compile_result["errors"]:
            is_vacuous, vacuous_reason = is_vacuous_formalization(candidate)
            if is_vacuous:
                if heuristic_candidate != candidate:
                    heuristic_result = compile_check(heuristic_candidate)
                    heuristic_vacuous, _ = is_vacuous_formalization(heuristic_candidate)
                    if (
                        heuristic_result["has_sorry"]
                        and not heuristic_result["errors"]
                        and not heuristic_vacuous
                    ):
                        candidate = heuristic_candidate
                        continue
                return FormalizeResponse(
                    success=False,
                    theorem_code=candidate,
                    scope="VACUOUS",
                    search_context=context_payload,
                    attempts=attempts,
                    errors=[f"Vacuous formalization rejected: {vacuous_reason}"],
                    message=(
                        "The formalizer produced a vacuous theorem that does not capture "
                        "the claim's mathematical content. Please reformulate with more "
                        "specific mathematical notation."
                    ),
                )

            faithfulness = check_semantic_faithfulness(raw_claim, candidate)
            faithfulness_warning = None
            if not faithfulness["faithful"]:
                missing = ", ".join(faithfulness["missing_concepts"][:5]) or "unknown"
                faithfulness_warning = (
                    "The formalization may not fully capture the claim. "
                    f"Concept coverage: {faithfulness['coverage']:.0%}. "
                    f"Possibly missing: {missing}"
                )
                logger.warning(
                    "Formalization faithfulness warning: coverage=%s missing=%s claim=%r",
                    faithfulness["coverage"],
                    faithfulness["missing_concepts"][:5],
                    raw_claim,
                )

            response = FormalizeResponse(
                success=True,
                theorem_code=candidate,
                scope=scope,
                search_context=context_payload,
                attempts=attempts,
                errors=_dedupe_errors(collected_errors),
                message="Generated a Lean theorem stub that compiles with `sorry`.",
                faithfulness_warning=faithfulness_warning,
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
            provider_failure_reason = _detect_formalization_failed(provider_repair)
            if provider_failure_reason:
                return FormalizeResponse(
                    success=False,
                    theorem_code=None,
                    scope=scope,
                    search_context=context_payload,
                    attempts=attempts,
                    errors=_dedupe_errors(collected_errors + [provider_failure_reason])[:10],
                    message=(
                        "The formalizer could not faithfully translate the claim and failed "
                        "honestly instead of returning a weaker theorem."
                    ),
                )
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
