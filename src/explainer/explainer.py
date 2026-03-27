"""Natural-language explanation helpers for verification results."""

from __future__ import annotations

from typing import Any

from mistralai.client import Mistral

from src.config import MISTRAL_API_KEY, MISTRAL_MODEL


def explain_verification_result(verification_result: dict[str, Any]) -> str:
    """Produce a compact explanation from a structured verification result."""

    status = verification_result.get("status", "unknown")
    theorem = verification_result.get("theorem", "theorem")
    attempts = verification_result.get("attempts", [])
    compile_info = verification_result.get("compile", {})
    errors = compile_info.get("errors") or verification_result.get("errors") or []

    if status == "verified":
        if attempts:
            return (
                f"{theorem} was verified by Lean after {len(attempts)} proof attempt(s). "
                "The kernel accepted the final proof term with no remaining `sorry`."
            )
        return f"{theorem} was verified by Lean and the kernel accepted the final proof."
    if status == "failed":
        blocker = errors[0] if errors else "the prover did not find a complete proof"
        return f"{theorem} was not verified. The main blocker was: {blocker}"
    return f"The verification status for {theorem} is {status}."


async def explain_verification_result_async(verification_result: dict[str, Any]) -> str:
    """Use Mistral when configured, otherwise fall back to the local summary."""

    fallback = explain_verification_result(verification_result)
    if not MISTRAL_API_KEY:
        return fallback

    client = Mistral(api_key=MISTRAL_API_KEY)
    prompt = (
        "Explain the following Lean verification result for a mathematically literate user. "
        "Be concise, mention whether the theorem was verified, and summarize the main blocker "
        "if it failed.\n\n"
        f"{verification_result}"
    )
    try:
        response = await client.chat.complete_async(
            model=MISTRAL_MODEL,
            temperature=0.2,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return fallback

    content = response.choices[0].message.content
    if isinstance(content, str) and content.strip():
        return content.strip()
    return fallback
