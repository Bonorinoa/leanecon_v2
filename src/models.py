"""Pydantic models for the LeanEcon v2 API surface."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LeanEconModel(BaseModel):
    """Base model that forbids undeclared fields."""

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(LeanEconModel):
    """Standard error payload."""

    detail: str = Field(description="Human-readable error message.")


class PreambleMatch(LeanEconModel):
    """Deterministic preamble or Lean asset match."""

    name: str = Field(description="Matched preamble or Lean artifact name.")
    path: str | None = Field(default=None, description="Relative file path.")
    score: float = Field(ge=0.0, description="Deterministic lexical match score.")
    reason: str = Field(description="Why the match was returned.")


class CuratedHint(LeanEconModel):
    """Hint bundle returned by deterministic retrieval."""

    name: str = Field(description="Hint bundle name.")
    description: str = Field(description="Why this hint may help.")
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that triggered this hint bundle.",
    )
    candidate_imports: list[str] = Field(
        default_factory=list,
        description="Suggested Lean imports to inspect next.",
    )
    candidate_identifiers: list[str] = Field(
        default_factory=list,
        description="Suggested Lean identifiers to inspect next.",
    )


class SearchRequest(LeanEconModel):
    """Request payload for deterministic retrieval."""

    raw_claim: str = Field(
        min_length=1,
        description="Natural-language claim or query to search for.",
    )
    domain: str = Field(
        default="economics",
        description="Requested domain tag for deterministic retrieval.",
    )


class SearchResponse(LeanEconModel):
    """Response payload for deterministic retrieval."""

    preamble_matches: list[PreambleMatch] = Field(default_factory=list)
    curated_hints: list[CuratedHint] = Field(default_factory=list)
    domain: str = Field(description="Resolved domain tag.")
    candidate_imports: list[str] = Field(default_factory=list)
    candidate_identifiers: list[str] = Field(default_factory=list)


class FormalizeRequest(LeanEconModel):
    """Request payload for statement formalization."""

    raw_claim: str = Field(min_length=1, description="Claim to formalize.")
    preamble_names: list[str] | None = Field(
        default=None,
        description="Optional preferred preamble entries supplied by the caller.",
    )


class FormalizeResponse(LeanEconModel):
    """Response payload for statement formalization."""

    success: bool = Field(description="Whether theorem-stub generation succeeded.")
    theorem_code: str | None = Field(
        default=None,
        description="Generated Lean theorem stub containing `sorry`.",
    )
    scope: Literal["IN_SCOPE", "NEEDS_DEFINITIONS", "RAW_LEAN", "VACUOUS"] = Field(
        description="Scope classification for the input claim.",
    )
    search_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Deterministic retrieval context used during formalization.",
    )
    attempts: int = Field(ge=0, description="Number of formalization attempts used.")
    errors: list[str] = Field(
        default_factory=list,
        description="Collected formalization errors and warnings.",
    )
    message: str | None = Field(
        default=None,
        description="Optional human-readable status message.",
    )
    faithfulness_warning: str | None = Field(
        default=None,
        description="Heuristic warning when the theorem may not preserve claim content.",
    )


class CompileRequest(LeanEconModel):
    """Request payload for direct Lean compilation."""

    lean_code: str = Field(min_length=1, description="Complete Lean source to compile.")


class CompileResponse(LeanEconModel):
    """Response payload for direct Lean compilation."""

    success: bool = Field(description="Whether compilation succeeded.")
    output: str = Field(description="Compiler stdout or summary.")
    errors: list[str] = Field(
        default_factory=list,
        description="Compiler errors and diagnostics.",
    )


class VerifyRequest(LeanEconModel):
    """Request payload for asynchronous verification."""

    theorem_with_sorry: str = Field(
        min_length=1,
        description="Lean theorem stub containing `sorry`.",
    )
    max_steps: int = Field(
        default=64,
        ge=1,
        le=512,
        description="Hard ceiling on agentic proving steps.",
    )
    timeout: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Verification timeout in seconds.",
    )


class VerifyAcceptedResponse(LeanEconModel):
    """Immediate response for queued verification jobs."""

    job_id: str = Field(description="Unique queued job identifier.")
    status: Literal["queued"] = Field(description="Initial queued status.")
    message: str = Field(description="Human-readable queue acknowledgement.")


class JobStatus(LeanEconModel):
    """Polling payload for asynchronous jobs."""

    id: str = Field(description="Job identifier.")
    status: str = Field(description="Current job status.")
    created_at: str = Field(description="Creation timestamp in ISO-8601 format.")
    updated_at: str = Field(description="Last update timestamp in ISO-8601 format.")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Structured result payload when the job has completed.",
    )
    error: str | None = Field(
        default=None,
        description="Error message when the job failed.",
    )


class ExplainRequest(LeanEconModel):
    """Request payload for explanation generation."""

    verification_result: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured verification result returned by the jobs API.",
    )


class ExplainResponse(LeanEconModel):
    """Response payload for explanation generation."""

    explanation: str = Field(description="Plain-language explanation.")


class HealthResponse(LeanEconModel):
    """Response payload for service health."""

    status: str = Field(description="Overall API status.")
    lean_available: bool = Field(description="Whether Lean is available.")
    driver: str = Field(description="Configured default driver name.")
    version: str = Field(description="API version string.")


class MetricsResponse(LeanEconModel):
    """Response payload for benchmark and operational metrics."""

    baselines: dict[str, Any] = Field(default_factory=dict)
    uptime: float = Field(ge=0.0, description="Seconds since API startup.")
    queue_depth: int = Field(default=0, ge=0, description="Queued verification jobs.")
    active_jobs: int = Field(default=0, ge=0, description="Currently running jobs.")


class NotImplementedResponse(LeanEconModel):
    """Response shape for scaffolded endpoints."""

    message: str = Field(description="Scaffold status message.")
