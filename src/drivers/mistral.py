"""Mistral drivers for LeanEcon v2 formalization and proving."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable

from mistralai.client import Mistral

from src.drivers.base import (
    DriverConfig,
    DriverEvent,
    ToolCall,
    ToolDefinition,
    ToolResult,
    register_formalizer,
    register_prover,
)


def _message_text(content: Any) -> str:
    """Normalize provider content blocks into plain text."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
                continue
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def _model_dump(message: Any) -> dict[str, Any]:
    """Serialize a provider message back into the next chat turn."""

    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if isinstance(message, dict):
        return message
    return {
        "role": getattr(message, "role", "assistant"),
        "content": _message_text(getattr(message, "content", "")),
    }


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    """Parse tool-call arguments into a dictionary."""

    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {"raw": arguments}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": arguments}


def _tool_schema(tool: ToolDefinition) -> dict[str, Any]:
    """Convert a LeanEcon tool definition into Mistral's JSON schema shape."""

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


@register_formalizer("mistral")
class MistralFormalizerDriver:
    """Single-turn Mistral adapter for theorem-stub generation."""

    def __init__(self, config: DriverConfig) -> None:
        self.config = config
        self._client: Mistral | None = None

    @property
    def name(self) -> str:
        return "mistral"

    async def formalize(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        """Run one chat completion and return the assistant text."""

        if not self.config.api_key:
            raise RuntimeError("MISTRAL_API_KEY is not configured.")
        if self._client is None:
            self._client = Mistral(api_key=self.config.api_key)
        response = await self._client.chat.complete_async(
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return _message_text(response.choices[0].message.content)


@register_prover("mistral")
class MistralProverDriver:
    """Tool-capable Mistral adapter for multi-step proving."""

    def __init__(self, config: DriverConfig) -> None:
        self.config = config
        self._client: Mistral | None = None

    @property
    def name(self) -> str:
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
        """Drive a bounded tool-use loop with the current Mistral chat API."""

        if not self.config.api_key:
            yield DriverEvent(type="error", data="MISTRAL_API_KEY is not configured.")
            return
        if self._client is None:
            self._client = Mistral(api_key=self.config.api_key)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        schemas = [_tool_schema(tool) for tool in tools]

        for step in range(1, max_steps + 1):
            response = await self._client.chat.complete_async(
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                messages=messages,
                tools=schemas,
                tool_choice="auto",
                parallel_tool_calls=False,
            )
            choice = response.choices[0]
            message = choice.message
            messages.append(_model_dump(message))

            assistant_text = _message_text(message.content)
            if assistant_text:
                yield DriverEvent(type="assistant", data={"step": step, "content": assistant_text})

            tool_calls = list(getattr(message, "tool_calls", []) or [])
            if tool_calls:
                for raw_call in tool_calls:
                    tool_call = ToolCall(
                        id=getattr(raw_call, "id", None) or f"tool_{step}",
                        name=raw_call.function.name,
                        arguments=_parse_arguments(raw_call.function.arguments),
                    )
                    yield DriverEvent(
                        type="tool_call",
                        data={
                            "step": step,
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        },
                    )
                    result = on_tool_call(tool_call)
                    yield DriverEvent(
                        type="tool_result",
                        data={
                            "step": step,
                            "name": tool_call.name,
                            "content": result.content,
                            "is_error": result.is_error,
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result.content,
                        }
                    )
                continue

            if choice.finish_reason in {"stop", "length"}:
                yield DriverEvent(type="done", data={"step": step, "content": assistant_text})
                return

        yield DriverEvent(type="error", data=f"Exceeded maximum proving steps ({max_steps}).")
