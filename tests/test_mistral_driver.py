"""Driver tests for the Mistral SDK adapter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.drivers.base import DriverConfig, ToolDefinition, ToolResult
from src.drivers.mistral import MistralFormalizerDriver, MistralProverDriver


def _fake_choice(message, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(message=message, finish_reason=finish_reason)


@pytest.mark.anyio
async def test_mistral_formalizer_driver_uses_sdk_kwargs(monkeypatch) -> None:
    """The driver should map generic config onto the current Mistral SDK."""

    captured: dict[str, object] = {}

    class FakeMistral:
        def __init__(self, **kwargs) -> None:
            captured["init_kwargs"] = kwargs
            self.chat = self

        async def complete_async(self, **kwargs):
            captured["request_kwargs"] = kwargs
            return SimpleNamespace(
                choices=[
                    _fake_choice(
                        SimpleNamespace(
                            content="import Mathlib\n\ntheorem demo : True := by\n  sorry\n"
                        )
                    )
                ]
            )

    monkeypatch.setattr("src.drivers.mistral.Mistral", FakeMistral)

    driver = MistralFormalizerDriver(
        DriverConfig(
            model="mistral-small",
            api_key="secret",
            base_url="https://api.example.test",
            temperature=0.2,
            timeout=12.5,
        )
    )
    output = await driver.formalize(system_prompt="system", user_prompt="user", max_tokens=256)

    assert "theorem demo" in output
    assert captured["init_kwargs"] == {
        "api_key": "secret",
        "server_url": "https://api.example.test",
        "timeout_ms": 12500,
    }
    assert captured["request_kwargs"]["model"] == "mistral-small"
    assert captured["request_kwargs"]["max_tokens"] == 256


@pytest.mark.anyio
async def test_mistral_formalizer_driver_wraps_sdk_failures(monkeypatch) -> None:
    """Provider exceptions should become clean runtime errors."""

    class FakeMistral:
        def __init__(self, **_kwargs) -> None:
            self.chat = self

        async def complete_async(self, **_kwargs):
            raise ValueError("bad gateway")

    monkeypatch.setattr("src.drivers.mistral.Mistral", FakeMistral)

    driver = MistralFormalizerDriver(DriverConfig(model="mistral-small", api_key="secret"))
    with pytest.raises(RuntimeError, match="Mistral request failed: ValueError: bad gateway"):
        await driver.formalize(system_prompt="system", user_prompt="user")


@pytest.mark.anyio
async def test_mistral_prover_driver_executes_tool_calls(monkeypatch) -> None:
    """The prover driver should loop tool calls back into the conversation."""

    captured_calls: list[dict[str, object]] = []

    tool_call = SimpleNamespace(
        id="tool_1",
        function=SimpleNamespace(name="search", arguments='{"query": "budget set"}'),
    )
    first_message = SimpleNamespace(content=None, tool_calls=[tool_call], role="assistant")
    final_message = SimpleNamespace(content="Finished.", tool_calls=[], role="assistant")

    class FakeMistral:
        def __init__(self, **_kwargs) -> None:
            self.chat = self
            self._responses = [
                SimpleNamespace(choices=[_fake_choice(first_message, finish_reason="tool_calls")]),
                SimpleNamespace(choices=[_fake_choice(final_message, finish_reason="stop")]),
            ]

        async def complete_async(self, **kwargs):
            captured_calls.append(kwargs)
            return self._responses.pop(0)

    monkeypatch.setattr("src.drivers.mistral.Mistral", FakeMistral)

    driver = MistralProverDriver(DriverConfig(model="mistral-small", api_key="secret"))
    invoked_tools: list[str] = []

    def on_tool_call(call):
        invoked_tools.append(call.name)
        return ToolResult(call.id, "search results")

    events = [
        event
        async for event in driver.prove(
            system_prompt="system",
            user_prompt="user",
            tools=[
                ToolDefinition(
                    name="search",
                    description="Search docs",
                    parameters={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                )
            ],
            on_tool_call=on_tool_call,
            max_steps=4,
        )
    ]

    assert invoked_tools == ["search"]
    assert [event.type for event in events] == ["tool_call", "tool_result", "assistant", "done"]
    tool_messages = [
        message for message in captured_calls[1]["messages"] if message.get("role") == "tool"
    ]
    assert tool_messages
    assert tool_messages[-1]["tool_call_id"] == "tool_1"
