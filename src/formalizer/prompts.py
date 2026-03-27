"""Prompt templates for statement formalization."""

FORMALIZER_SYSTEM_PROMPT = """
You are the LeanEcon v2 formalizer.
Produce a Lean 4 theorem stub with `sorry`.
Preserve economic meaning and prefer explicit assumptions.
""".strip()

FORMALIZER_USER_PROMPT_TEMPLATE = """
Claim:
{raw_claim}

Search context:
{search_context}
""".strip()
