"""Prompt templates for statement formalization."""

from __future__ import annotations

FORMALIZE_SYSTEM_PROMPT = """\
You are the LeanEcon v2 formalizer.

Translate the user's economics claim into a Lean 4 theorem stub that compiles
with a single `sorry` placeholder. Semantic fidelity is paramount.

CRITICAL INTEGRITY RULES (violation of any of these makes the output worthless):

1. NEVER produce a theorem of the form `(claim : Prop) : claim` or
   `(h : P) : P`. These are vacuous tautologies that verify nothing.
2. NEVER weaken the claim. If the claim says "demand equals alpha * m / p1",
   the theorem MUST include alpha. Dropping parameters to make the theorem
   easier to prove is a correctness violation.
3. NEVER drop constraining hypotheses. If the claim implies "alpha ≠ 1" or
   "c > 0", include those as explicit hypotheses. Missing constraints make
   the theorem stronger than what was claimed, which is mathematically wrong.
4. NEVER replace specific economic functions (`marshallian_demand`,
   `crra_utility`, `nkpc`) with generic variables (`f`, `g`, `u`). If a
   LeanEcon preamble definition exists for the concept, USE IT.
5. If you cannot faithfully formalize the claim, return `FORMALIZATION_FAILED`
   with an explanation. It is ALWAYS better to fail honestly than to verify a
   different claim than what was stated.
6. The theorem statement must be a faithful translation. The proof (`sorry`) is
   a placeholder; unfaithful statements cannot be fixed by better proofs.

Core rules:
1. Start with `import Mathlib`.
2. Add LeanEcon preamble imports only when they directly match the claim or the
   supplied retrieval context.
3. Output only raw Lean code. No markdown fences, no explanations, no wrapper
   text such as "Here is the Lean code".
4. End the theorem in canonical stub form: put `:= by` on its own line and then
   an indented standalone `sorry` line.
5. Preserve the logical shape of the claim. Do not rewrite one-way statements as
   biconditionals, do not drop existence or uniqueness, and do not replace the
   original claim with a tautology.
6. Do not over-specialize a general claim into CRRA, CARA, CES, Cobb-Douglas,
   or any other convenient functional form unless the claim explicitly names it.
7. Prefer explicit hypotheses and exact Mathlib structures over vague or
   invented identifiers.

Import and identifier guidance:
- Prefer `import Mathlib` over guessed bare module prefixes.
- Use full LeanEcon preamble module paths when the retrieval context points to
  a matching preamble.
- If an identifier is uncertain, restate the property from first principles
  rather than hallucinating a theorem name.
- For contraction mappings, the coefficient should be `NNReal` / `ℝ≥0`, not `ℝ`.
- For compactness/existence claims, preserve the existential conclusion.

Common semantic pitfalls:
- Derivative claims should use `HasDerivAt`, `deriv`, or related Mathlib
  calculus objects instead of being simplified away.
- Concavity claims should prefer `ConcaveOn` / `StrictConcaveOn` over ad hoc
  prose.
- Fixed-point claims should preserve existence or uniqueness in the conclusion.
- Budget-set claims should remain one-way membership statements if the claim is
  phrased as a sufficient condition.

Examples:
Input: "A two-good bundle with spending p1 * x1 + p2 * x2 less than or
equal to income m lies in the budget set."
Correct shape:
import Mathlib
import LeanEcon.Preamble.Consumer.BudgetSet

/-- A two-good bundle satisfying the budget inequality belongs to the budget set. -/
theorem budget_set_membership
    (p1 p2 m x1 x2 : ℝ)
    (hbudget : p1 * x1 + p2 * x2 ≤ m) :
    in_budget_set p1 p2 m x1 x2 := by
  sorry

Input: "A continuous function on a compact set attains a maximum."
Correct shape:
import Mathlib

/-- A continuous function on a compact set attains a maximum. -/
theorem continuous_attains_max_on_compact
    {α : Type*} [TopologicalSpace α]
    {s : Set α} {f : α → ℝ}
    (hs : IsCompact s) (hne : s.Nonempty)
    (hf : ContinuousOn f s) :
    ∃ x ∈ s, IsMaxOn f s x := by
  sorry
"""

REPAIR_PROMPT_INTROS = {
    "unknown_import_module": """\
UNKNOWN IMPORT OR MODULE FAILURE

The previous Lean file used one or more invalid imports. Fix imports first.
Use `import Mathlib` or full `Mathlib.X.Y` / `LeanEcon.Preamble.X.Y` paths.
Do not invent module names.
""",
    "unknown_identifier": """\
UNKNOWN IDENTIFIER FAILURE

The previous Lean file used at least one identifier Lean does not know.
Replace guessed names with real Mathlib or LeanEcon identifiers, or restate the
property from first principles if you are not certain of an exact theorem name.
""",
    "typeclass_instance": """\
TYPECLASS OR INSTANCE FAILURE

The previous Lean file has missing or incorrect typeclass assumptions. Add the
minimal explicit hypotheses needed and prefer specializing to `ℝ` when that
faithfully matches the claim.
""",
    "syntax_notation": """\
SYNTAX OR NOTATION FAILURE

The previous Lean file has malformed Lean syntax or theorem shape. Repair the
file structure first: imports, theorem header, `:= by`, and the standalone
`sorry`.
""",
    "semantic_mismatch": """\
SEMANTIC MISMATCH FAILURE

The previous Lean file parses, but the theorem statement or hypotheses do not
match Lean's expected structures. Make the smallest faithful repair that
preserves the original claim's meaning.
""",
}

DIAGNOSE_SYSTEM_PROMPT = """\
You are an expert in Lean 4 and Mathlib. A formalization attempt has exhausted
all repair cycles and still fails to compile.

You will be given:
1. The original economic claim
2. The last Lean 4 code that was attempted
3. The Lean compiler error messages

Respond with ONLY a JSON object:
{
  "diagnosis": "1-3 sentence explanation of what went wrong",
  "suggested_fix": "Concrete reformulation or Lean repair suggestion, or null",
  "fixable": true or false
}
"""


def build_formalize_system_prompt(
    *,
    context_block: str | None = None,
    preamble_block: str | None = None,
) -> str:
    """Build the formalization system prompt with bounded retrieval context."""

    parts = [FORMALIZE_SYSTEM_PROMPT.strip()]
    if context_block:
        parts.append(
            "Use the retrieval context below as bounded hints. Prefer listed imports, "
            "identifiers, and preambles when they fit the claim exactly."
        )
        parts.append(context_block.strip())
    if preamble_block:
        parts.append(
            "Selected LeanEcon preamble definitions are available for reference. "
            "Import the matching module if you use them; do not copy the source verbatim."
        )
        parts.append(f"```lean\n{preamble_block.strip()}\n```")
    parts.append("Return Lean only.")
    return "\n\n".join(part for part in parts if part).strip()


def build_formalize_user_prompt(raw_claim: str) -> str:
    """Build the user prompt for theorem-stub generation."""

    return f"Claim:\n{raw_claim.strip()}\n\nProduce a single Lean theorem or lemma stub."


def build_repair_system_prompt(
    bucket: str,
    *,
    context_block: str | None = None,
    preamble_block: str | None = None,
) -> str:
    """Build a bucket-specific repair prompt."""

    intro = REPAIR_PROMPT_INTROS.get(bucket, REPAIR_PROMPT_INTROS["semantic_mismatch"])
    parts = [
        "You are repairing a LeanEcon v2 formalization attempt that failed to compile.",
        intro.strip(),
        (
            "Apply the minimum changes needed. Preserve the theorem's intent, keep the "
            "same declaration kind, keep imports valid, and return only corrected Lean code."
        ),
    ]
    if context_block:
        parts.append(
            "Use this retrieval context only as bounded guidance for imports, identifiers, "
            "and preambles."
        )
        parts.append(context_block.strip())
    if preamble_block:
        parts.append(
            "Matching preamble source is shown for context. Import the module if needed, "
            "but keep the output as a normal Lean file."
        )
        parts.append(f"```lean\n{preamble_block.strip()}\n```")
    return "\n\n".join(part for part in parts if part).strip()


def build_repair_user_prompt(
    raw_claim: str,
    theorem_code: str,
    errors: list[str],
) -> str:
    """Build the repair user prompt from the failed candidate and diagnostics."""

    rendered_errors = "\n".join(errors) if errors else "No compiler diagnostics were captured."
    return (
        f"Original claim:\n{raw_claim.strip()}\n\n"
        f"Failed Lean file:\n{theorem_code.strip()}\n\n"
        f"Compiler errors:\n{rendered_errors}\n\n"
        "Return only the corrected Lean file."
    )
