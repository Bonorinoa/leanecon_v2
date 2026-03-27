"""Mistral driver scaffold for LeanEcon v2."""

from __future__ import annotations

from typing import AsyncIterator, Callable

from src.config import COMING_SOON_MESSAGE
from src.drivers.base import (
    DriverConfig,
    DriverEvent,
    ToolCall,
    ToolDefinition,
    ToolResult,
    register_formalizer,
    register_prover,
)


@register_prover("mistral")
@register_formalizer("mistral")
class MistralDriver:
    """Phase 2A Mistral adapter placeholder."""

    def __init__(self, config: DriverConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        """Return the provider name."""

        return "mistral"

    async def prove(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[ToolDefinition],
        on_tool_call: Callable[[ToolCall], ToolResult],
        max_steps: int = 64,
    ) -> AsyncIterator[DriverEvent]:
        """Yield a single placeholder error event until Phase 3 lands."""

        _ = (system_prompt, user_prompt, tools, on_tool_call, max_steps)
        yield DriverEvent(type="error", data=COMING_SOON_MESSAGE)

    async def formalize(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        """Return a placeholder status string until Phase 3 lands."""

        _ = (system_prompt, user_prompt, max_tokens)
        return COMING_SOON_MESSAGE
