"""Google Gemini drivers for LeanEcon v2 formalization and proving."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable

from google import genai
from google.genai import types

from src.drivers.base import (
    DriverConfig,
    DriverEvent,
    ToolCall,
    ToolDefinition,
    ToolResult,
    register_formalizer,
    register_prover,
)


def _client_kwargs(config: DriverConfig) -> dict[str, Any]:
    """Map provider-agnostic config onto the current Gemini SDK."""

    kwargs: dict[str, Any] = {"api_key": config.api_key}
    if config.timeout:
        kwargs["http_options"] = types.HttpOptions(timeout=config.timeout)
    return kwargs


def _provider_error_message(exc: Exception) -> str:
    """Render one provider failure as a concise user-facing message."""

    return f"Gemini request failed: {exc.__class__.__name__}: {exc}"


def _response_content(response: Any) -> Any | None:
    """Return the first candidate content block when present."""

    try:
        return response.candidates[0].content
    except (AttributeError, IndexError, TypeError):
        return None


def _response_parts(response: Any) -> list[Any]:
    """Return response parts in a shape we can iterate over safely."""

    content = _response_content(response)
    if content is not None:
        return list(getattr(content, "parts", []) or [])
    return list(getattr(response, "parts", []) or [])


def _response_text(response: Any) -> str:
    """Extract plain assistant text from a Gemini response."""

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    parts: list[str] = []
    for part in _response_parts(response):
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str) and part_text.strip():
            parts.append(part_text.strip())
    return "\n".join(parts).strip()


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    """Normalize Gemini function-call arguments to a dictionary."""

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


def _tool_schema(tool: ToolDefinition) -> types.Tool:
    """Convert a LeanEcon tool definition into Gemini's tool schema."""

    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=tool.parameters,
            )
        ]
    )


def _response_tool_calls(response: Any) -> list[Any]:
    """Extract Gemini function-call parts from one response."""

    tool_calls: list[Any] = []
    for part in _response_parts(response):
        function_call = getattr(part, "function_call", None)
        if function_call is not None:
            tool_calls.append(function_call)
    return tool_calls


@register_formalizer("gemini")
class GeminiFormalizerDriver:
    """Single-turn Gemini adapter for theorem-stub generation."""

    def __init__(self, config: DriverConfig) -> None:
        self.config = config
        self._client = None

    @property
    def name(self) -> str:
        return "gemini"

    async def formalize(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        """Run one generate-content call and return the assistant text."""

        if not self.config.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        if self._client is None:
            self._client = genai.Client(**_client_kwargs(self.config)).aio

        try:
            response = await self._client.models.generate_content(
                model=self.config.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self.config.temperature,
                    max_output_tokens=max_tokens,
                ),
            )
        except Exception as exc:  # pragma: no cover - exact SDK failures are mocked in tests.
            raise RuntimeError(_provider_error_message(exc)) from exc

        output = _response_text(response)
        if output:
            return output
        raise RuntimeError("Gemini response did not include assistant text.")


@register_prover("gemini")
class GeminiProverDriver:
    """Tool-capable Gemini adapter for multi-step proving."""

    def __init__(self, config: DriverConfig) -> None:
        self.config = config
        self._client = None

    @property
    def name(self) -> str:
        return "gemini"

    async def prove(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[ToolDefinition],
        on_tool_call: Callable[[ToolCall], ToolResult],
        max_steps: int = 64,
    ) -> AsyncIterator[DriverEvent]:
        """Drive a bounded Gemini tool loop."""

        if not self.config.api_key:
            yield DriverEvent(type="error", data="GEMINI_API_KEY is not configured.")
            return
        if self._client is None:
            self._client = genai.Client(**_client_kwargs(self.config)).aio

        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]),
        ]
        schemas = [_tool_schema(tool) for tool in tools]
        request_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            tools=schemas,
        )

        for step in range(1, max_steps + 1):
            try:
                response = await self._client.models.generate_content(
                    model=self.config.model,
                    contents=contents,
                    config=request_config,
                )
            except Exception as exc:  # pragma: no cover - exact SDK failures are mocked in tests.
                yield DriverEvent(type="error", data=_provider_error_message(exc))
                return

            content = _response_content(response)
            if content is None:
                yield DriverEvent(
                    type="error",
                    data="Gemini response did not include a valid assistant candidate.",
                )
                return

            contents.append(content)

            assistant_text = _response_text(response)
            if assistant_text:
                yield DriverEvent(type="assistant", data={"step": step, "content": assistant_text})

            tool_calls = _response_tool_calls(response)
            if tool_calls:
                for index, raw_call in enumerate(tool_calls, start=1):
                    tool_call = ToolCall(
                        id=getattr(raw_call, "id", None) or f"tool_{step}_{index}",
                        name=str(getattr(raw_call, "name", "")),
                        arguments=_parse_arguments(getattr(raw_call, "args", None)),
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
                    response_payload = (
                        {"error": result.content} if result.is_error else {"output": result.content}
                    )
                    contents.append(
                        types.Content(
                            role="tool",
                            parts=[
                                types.Part.from_function_response(
                                    name=tool_call.name,
                                    response=response_payload,
                                )
                            ],
                        )
                    )
                continue

            yield DriverEvent(type="done", data={"step": step, "content": assistant_text})
            return

        yield DriverEvent(type="error", data=f"Exceeded maximum proving steps ({max_steps}).")
