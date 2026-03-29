"""Shared runtime config resolution for provider-backed drivers."""

from __future__ import annotations

from src.config import (
    DEFAULT_DRIVER,
    GOAL_ANALYST_API_KEY,
    GOAL_ANALYST_DRIVER,
    GOAL_ANALYST_MAX_TOKENS,
    GOAL_ANALYST_MODEL,
    GOAL_ANALYST_TEMPERATURE,
    GOAL_ANALYST_TIMEOUT,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MISTRAL_API_KEY,
    MISTRAL_MODEL,
)
from src.drivers.base import DriverConfig


def provider_model_and_api_key(driver_name: str | None = None) -> tuple[str, str]:
    """Return the configured model name and API key for one provider."""

    selected_driver = driver_name or DEFAULT_DRIVER
    if selected_driver == "mistral":
        return MISTRAL_MODEL, MISTRAL_API_KEY
    if selected_driver == "gemini":
        return GEMINI_MODEL, GEMINI_API_KEY
    raise ValueError(f"Unsupported provider driver '{selected_driver}'.")


def provider_driver_config(
    *,
    temperature: float,
    driver_name: str | None = None,
    max_tokens: int = 4096,
    timeout: float = 300.0,
) -> DriverConfig:
    """Build a generic driver config for the selected runtime provider."""

    model, api_key = provider_model_and_api_key(driver_name)
    return DriverConfig(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def _goal_analyst_default_model(driver_name: str) -> str:
    if driver_name == "mistral":
        return "open-mistral-nemo"
    if driver_name == "gemini":
        return "gemini-2.0-flash-lite"
    return ""


def goal_analyst_driver_and_config() -> tuple[str, DriverConfig]:
    """Return the configured fast-model setup for Goal Analyst hints."""

    selected_driver = GOAL_ANALYST_DRIVER or DEFAULT_DRIVER
    provider_model, provider_api_key = provider_model_and_api_key(selected_driver)
    model = GOAL_ANALYST_MODEL or _goal_analyst_default_model(selected_driver) or provider_model
    api_key = GOAL_ANALYST_API_KEY or provider_api_key
    return (
        selected_driver,
        DriverConfig(
            model=model,
            api_key=api_key,
            temperature=GOAL_ANALYST_TEMPERATURE,
            max_tokens=GOAL_ANALYST_MAX_TOKENS,
            timeout=GOAL_ANALYST_TIMEOUT,
        ),
    )
