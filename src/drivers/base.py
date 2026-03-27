"""Provider-agnostic interface for LLM-driven proving and formalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolDefinition:
    """A tool that the LLM can call during proving."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    """A tool call emitted by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Result of executing a tool call."""

    call_id: str
    content: str
    is_error: bool = False


@dataclass
class DriverEvent:
    """Progress event from the driver."""

    type: str
    data: Any = None


@dataclass
class DriverConfig:
    """Configuration for a driver instance."""

    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 1.0
    max_tokens: int = 4096
    timeout: float = 300.0
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ProverDriver(Protocol):
    """Provider-agnostic interface for LLM-driven agentic proving.

    Implementors handle the provider-specific API (Mistral, Gemini, HF, etc.)
    and expose a uniform async iteration interface. The proving harness manages
    tool execution, budget tracking, and file control; the driver just manages
    the LLM conversation loop.
    """

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g. 'mistral', 'gemini')."""

    async def prove(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[ToolDefinition],
        on_tool_call: Callable[[ToolCall], ToolResult],
        max_steps: int = 64,
    ) -> AsyncIterator[DriverEvent]:
        """Drive a proving loop.

        The driver sends the system/user prompts to the LLM, handles tool-use
        turns by calling on_tool_call for each tool invocation, and yields
        DriverEvents for progress tracking.

        The driver MUST:
        - Call on_tool_call for every tool call the LLM emits
        - Feed tool results back into the conversation
        - Yield DriverEvent(type="done") when the LLM signals completion
        - Yield DriverEvent(type="error") on unrecoverable failures
        - Respect max_steps as a hard ceiling on conversation turns

        The driver MUST NOT:
        - Execute tools itself (that's the harness's job via on_tool_call)
        - Manage proof files or checkpoints
        - Make decisions about proof strategy
        """


@runtime_checkable
class FormalizerDriver(Protocol):
    """Provider-agnostic interface for LLM-driven formalization.

    Simpler than ProverDriver — no tool-use loop, just a single
    structured generation call.
    """

    @property
    def name(self) -> str:
        """Human-readable provider name."""

    async def formalize(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a Lean 4 theorem stub from the prompt.

        Returns the raw LLM output string. The formalizer module handles
        parsing, validation, and retry logic.
        """


_prover_drivers: dict[str, type[Any]] = {}
_formalizer_drivers: dict[str, type[Any]] = {}


def register_prover(name: str):
    """Decorator to register a ProverDriver implementation."""

    def decorator(cls: type[Any]) -> type[Any]:
        _prover_drivers[name] = cls
        return cls

    return decorator


def register_formalizer(name: str):
    """Decorator to register a FormalizerDriver implementation."""

    def decorator(cls: type[Any]) -> type[Any]:
        _formalizer_drivers[name] = cls
        return cls

    return decorator


def get_prover_driver(name: str, config: DriverConfig) -> ProverDriver:
    """Instantiate a registered ProverDriver by name."""

    if name not in _prover_drivers:
        available = ", ".join(_prover_drivers.keys()) or "(none)"
        raise ValueError(f"Unknown prover driver '{name}'. Available: {available}")
    return _prover_drivers[name](config)


def get_formalizer_driver(name: str, config: DriverConfig) -> FormalizerDriver:
    """Instantiate a registered FormalizerDriver by name."""

    if name not in _formalizer_drivers:
        available = ", ".join(_formalizer_drivers.keys()) or "(none)"
        raise ValueError(f"Unknown formalizer driver '{name}'. Available: {available}")
    return _formalizer_drivers[name](config)
