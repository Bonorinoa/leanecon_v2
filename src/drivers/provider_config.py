"""Shared runtime config resolution for provider-backed drivers."""

from __future__ import annotations

from src.config import (
    DEFAULT_DRIVER,
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
