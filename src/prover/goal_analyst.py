"""Lightweight tactic-failure analysis for prover tool loops."""

from __future__ import annotations

import re
from typing import Any

from src.drivers.provider_config import goal_analyst_driver_and_config


def _build_system_prompt() -> str:
    return (
        "You are Goal Analyst for Lean 4 proof search. "
        "Given one failed tactic attempt, return exactly one or two short sentences "
        "that suggest the next action. Be concrete and deterministic."
    )


def _build_user_prompt(
    *,
    tactic: str,
    lean_error: str,
    goals: list[str],
    tactic_history: list[str],
) -> str:
    goals_block = "\n".join(f"- {goal}" for goal in goals[:3]) or "- (no goals reported)"
    history_block = "\n".join(f"- {step}" for step in tactic_history[-6:]) or "- (none)"
    return (
        "Failed tactic:\n"
        f"{tactic}\n\n"
        "Lean error:\n"
        f"{lean_error}\n\n"
        "Current goals:\n"
        f"{goals_block}\n\n"
        "Recent tactic history:\n"
        f"{history_block}\n\n"
        "Return one or two plain sentences only."
    )


def _normalize_hint(raw: str | None) -> str | None:
    if not raw:
        return None
    compact = " ".join(raw.replace("\n", " ").split()).strip()
    if not compact:
        return None
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", compact) if part.strip()]
    hint = " ".join(parts[:2]).strip() if parts else compact
    if len(hint) > 280:
        hint = hint[:277].rsplit(" ", 1)[0] + "..."
    return hint or None


def _mistral_hint(system_prompt: str, user_prompt: str, config: Any) -> str | None:
    from mistralai.client import Mistral

    kwargs: dict[str, Any] = {"api_key": config.api_key}
    if config.timeout:
        kwargs["timeout_ms"] = max(1, int(config.timeout * 1000))
    client = Mistral(**kwargs)
    response = client.chat.complete(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        return None

    if isinstance(content, str):
        return _normalize_hint(content)
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"].strip())
        return _normalize_hint(" ".join(chunks))
    return _normalize_hint(str(content))


def _gemini_hint(system_prompt: str, user_prompt: str, config: Any) -> str | None:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.api_key)
    response = client.models.generate_content(
        model=config.model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
        ),
    )

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return _normalize_hint(text)

    parts: list[Any] = []
    try:
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0]
        content = getattr(candidate, "content", None)
        if content is not None:
            parts = list(getattr(content, "parts", []) or [])
    except (AttributeError, IndexError, TypeError):
        parts = []

    chunks: list[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str) and part_text.strip():
            chunks.append(part_text.strip())
    return _normalize_hint(" ".join(chunks))


def generate_goal_analyst_hint(
    *,
    tactic: str,
    lean_error: str,
    goals: list[str],
    tactic_history: list[str],
) -> str | None:
    """Return a concise hint for one failed tactic, or None on any failure."""

    driver_name, config = goal_analyst_driver_and_config()
    if not config.api_key:
        return None

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(
        tactic=tactic,
        lean_error=lean_error,
        goals=goals,
        tactic_history=tactic_history,
    )

    try:
        if driver_name == "mistral":
            return _mistral_hint(system_prompt, user_prompt, config)
        if driver_name == "gemini":
            return _gemini_hint(system_prompt, user_prompt, config)
    except Exception:
        return None
    return None
