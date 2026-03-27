"""FastAPI application for LeanEcon v2."""

from __future__ import annotations

from time import monotonic

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from src.config import APP_VERSION, COMING_SOON_MESSAGE, CORS_ORIGINS, DEFAULT_DRIVER
from src.models import (
    CompileRequest,
    ErrorResponse,
    ExplainRequest,
    FormalizeRequest,
    HealthResponse,
    JobStatus,
    MetricsResponse,
    SearchRequest,
    SearchResponse,
    VerifyRequest,
)
from src.search.engine import search_claim

START_TIME = monotonic()

app = FastAPI(
    title="LeanEcon v2",
    description="Formal verification API for mathematical economics claims",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _not_implemented() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=COMING_SOON_MESSAGE,
    )


def _health_payload() -> HealthResponse:
    return HealthResponse(
        status="ok",
        lean_available=False,
        driver=DEFAULT_DRIVER,
        version=APP_VERSION,
    )


@app.get("/health", response_model=HealthResponse, responses={500: {"model": ErrorResponse}})
async def health() -> HealthResponse:
    """Return service liveness and alpha environment state."""

    return _health_payload()


@app.post(
    "/api/v2/search",
    response_model=SearchResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def search(request: SearchRequest) -> SearchResponse:
    """Run deterministic retrieval without calling any LLM provider."""

    return search_claim(request.raw_claim, request.domain)


@app.post("/api/v2/formalize")
async def formalize(request: FormalizeRequest) -> dict[str, str]:
    """Phase 2A placeholder for theorem-stub generation."""

    _ = request
    raise _not_implemented()


@app.post("/api/v2/compile")
async def compile_endpoint(request: CompileRequest) -> dict[str, str]:
    """Phase 2A placeholder for direct Lean compilation."""

    _ = request
    raise _not_implemented()


@app.post("/api/v2/verify", status_code=status.HTTP_202_ACCEPTED)
async def verify(request: VerifyRequest) -> dict[str, str]:
    """Phase 2A placeholder for async proof generation and verification."""

    _ = request
    raise _not_implemented()


@app.get("/api/v2/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    """Phase 2A placeholder for job polling."""

    _ = job_id
    raise _not_implemented()


@app.get("/api/v2/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> dict[str, str]:
    """Phase 2A placeholder for SSE job progress."""

    _ = job_id
    raise _not_implemented()


@app.post("/api/v2/explain")
async def explain(request: ExplainRequest) -> dict[str, str]:
    """Phase 2A placeholder for natural-language explanations."""

    _ = request
    raise _not_implemented()


@app.get("/api/v2/metrics", response_model=MetricsResponse)
async def metrics() -> MetricsResponse:
    """Phase 2A placeholder for benchmark and telemetry snapshots."""

    _ = START_TIME
    raise _not_implemented()
