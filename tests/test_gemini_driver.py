"""Driver tests for the Gemini SDK adapter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.drivers.base import DriverConfig, ToolDefinition, ToolResult
from src.drivers.gemini import GeminiFormalizerDriver, GeminiProverDriver
from src.drivers.registry import get_formalizer_driver, get_prover_driver


def _fake_response(*, parts, text: str | None = None):
    content = SimpleNamespace(parts=parts, role="model")
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)], text=text)


@pytest.mark.anyio
async def test_gemini_formalizer_driver_uses_sdk_kwargs(monkeypatch) -> None:
    """The driver should map generic config onto the current Gemini SDK."""

    captured: dict[str, object] = {}

    class FakeHttpOptions:
        def __init__(self, **kwargs) -> None:
            self.timeout = kwargs.get("timeout")

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs) -> None:
            self.system_instruction = kwargs.get("system_instruction")
            self.temperature = kwargs.get("temperature")
            self.max_output_tokens = kwargs.get("max_output_tokens")
            self.tools = kwargs.get("tools")

    fake_types = SimpleNamespace(
        HttpOptions=FakeHttpOptions,
        GenerateContentConfig=FakeGenerateContentConfig,
    )

    class FakeAsyncClient:
        def __init__(self) -> None:
            self.models = self

        async def generate_content(self, **kwargs):
            captured["request_kwargs"] = kwargs
            return _fake_response(
                parts=[SimpleNamespace(text="theorem demo : True := by\n  sorry\n")],
                text="theorem demo : True := by\n  sorry\n",
            )

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["init_kwargs"] = kwargs
            self.aio = FakeAsyncClient()

    monkeypatch.setattr("src.drivers.gemini.types", fake_types)
    monkeypatch.setattr("src.drivers.gemini.genai.Client", FakeClient)

    driver = GeminiFormalizerDriver(
        DriverConfig(
            model="gemini-3.1-pro-preview",
            api_key="secret",
            temperature=0.2,
            timeout=12.5,
        )
    )
    output = await driver.formalize(system_prompt="system", user_prompt="user", max_tokens=256)

    assert "theorem demo" in output
    assert captured["init_kwargs"]["api_key"] == "secret"
    assert captured["init_kwargs"]["http_options"].timeout == 12.5
    assert captured["request_kwargs"]["model"] == "gemini-3.1-pro-preview"
    assert captured["request_kwargs"]["contents"] == "user"
    assert captured["request_kwargs"]["config"].system_instruction == "system"
    assert captured["request_kwargs"]["config"].temperature == 0.2
    assert captured["request_kwargs"]["config"].max_output_tokens == 256


@pytest.mark.anyio
async def test_gemini_formalizer_driver_wraps_sdk_failures(monkeypatch) -> None:
    """Provider exceptions should become clean runtime errors."""

    class FakeAsyncClient:
        def __init__(self) -> None:
            self.models = self

        async def generate_content(self, **_kwargs):
            raise ValueError("bad gateway")

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            self.aio = FakeAsyncClient()

    monkeypatch.setattr("src.drivers.gemini.genai.Client", FakeClient)

    driver = GeminiFormalizerDriver(DriverConfig(model="gemini-3.1-pro-preview", api_key="secret"))
    with pytest.raises(RuntimeError, match="Gemini request failed: ValueError: bad gateway"):
        await driver.formalize(system_prompt="system", user_prompt="user")


@pytest.mark.anyio
async def test_gemini_prover_driver_executes_tool_calls(monkeypatch) -> None:
    """The prover driver should loop Gemini tool calls back into the conversation."""

    captured_calls: list[dict[str, object]] = []
    tool_responses: list[dict[str, object]] = []

    class FakeHttpOptions:
        def __init__(self, **kwargs) -> None:
            self.timeout = kwargs.get("timeout")

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs) -> None:
            self.system_instruction = kwargs.get("system_instruction")
            self.temperature = kwargs.get("temperature")
            self.max_output_tokens = kwargs.get("max_output_tokens")
            self.tools = kwargs.get("tools")

    class FakeFunctionDeclaration:
        def __init__(self, **kwargs) -> None:
            self.name = kwargs.get("name")
            self.description = kwargs.get("description")
            self.parameters_json_schema = kwargs.get("parameters_json_schema")

    class FakeTool:
        def __init__(self, **kwargs) -> None:
            self.function_declarations = kwargs.get("function_declarations")

    class FakeContent:
        def __init__(self, *, role, parts) -> None:
            self.role = role
            self.parts = parts

    class FakePartFactory:
        @staticmethod
        def from_text(*, text):
            return SimpleNamespace(text=text)

        @staticmethod
        def from_function_response(*, name, response):
            tool_responses.append({"name": name, "response": response})
            return SimpleNamespace(function_response=SimpleNamespace(name=name, response=response))

    fake_types = SimpleNamespace(
        HttpOptions=FakeHttpOptions,
        GenerateContentConfig=FakeGenerateContentConfig,
        FunctionDeclaration=FakeFunctionDeclaration,
        Tool=FakeTool,
        Content=FakeContent,
        Part=FakePartFactory,
    )

    first_response = _fake_response(
        parts=[
            SimpleNamespace(
                function_call=SimpleNamespace(
                    id="tool_1",
                    name="search",
                    args={"query": "budget set"},
                )
            )
        ]
    )
    second_response = _fake_response(parts=[SimpleNamespace(text="Finished.")], text="Finished.")

    class FakeAsyncClient:
        def __init__(self) -> None:
            self.models = self
            self._responses = [first_response, second_response]

        async def generate_content(self, **kwargs):
            frozen_kwargs = dict(kwargs)
            contents = kwargs.get("contents")
            if isinstance(contents, list):
                frozen_kwargs["contents"] = list(contents)
            captured_calls.append(frozen_kwargs)
            return self._responses.pop(0)

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            self.aio = FakeAsyncClient()

    monkeypatch.setattr("src.drivers.gemini.types", fake_types)
    monkeypatch.setattr("src.drivers.gemini.genai.Client", FakeClient)

    driver = GeminiProverDriver(DriverConfig(model="gemini-3.1-pro-preview", api_key="secret"))
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
    assert captured_calls[0]["config"].system_instruction == "system"
    assert captured_calls[0]["config"].tools[0].function_declarations[0].name == "search"
    assert captured_calls[1]["contents"][-1].role == "tool"
    assert tool_responses[-1] == {"name": "search", "response": {"output": "search results"}}


def test_gemini_driver_registered() -> None:
    """The Gemini driver should appear in the runtime registry."""

    from src.drivers.registry import available_formalizer_drivers, available_prover_drivers

    assert "gemini" in available_prover_drivers()
    assert "gemini" in available_formalizer_drivers()


def test_driver_selection_via_config() -> None:
    """Both provider drivers should instantiate through the common registry."""

    config = DriverConfig(model="test", api_key="fake")
    mistral_prover = get_prover_driver("mistral", config)
    gemini_prover = get_prover_driver("gemini", config)
    mistral_formalizer = get_formalizer_driver("mistral", config)
    gemini_formalizer = get_formalizer_driver("gemini", config)

    assert mistral_prover.name == "mistral"
    assert gemini_prover.name == "gemini"
    assert mistral_formalizer.name == "mistral"
    assert gemini_formalizer.name == "gemini"


def test_provider_driver_config_selects_gemini_runtime(monkeypatch) -> None:
    """Runtime config selection should follow LEANECON_DRIVER for Gemini."""

    from src.drivers import provider_config

    monkeypatch.setattr(provider_config, "DEFAULT_DRIVER", "gemini")
    monkeypatch.setattr(provider_config, "GEMINI_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setattr(provider_config, "GEMINI_API_KEY", "gemini-secret")

    config = provider_config.provider_driver_config(temperature=0.7)

    assert config.model == "gemini-3.1-pro-preview"
    assert config.api_key == "gemini-secret"
    assert config.temperature == 0.7
