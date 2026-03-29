"""FastAPI application for LeanEcon v2."""

from __future__ import annotations

import asyncio
import json
import sys
from time import monotonic
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.config import (
    APP_VERSION,
    CORS_ORIGINS,
    DEFAULT_DRIVER,
    EVAL_CLAIMS_DIR,
    FORMALIZE_TEMPERATURE,
    PROVE_TEMPERATURE,
)
from src.drivers.provider_config import provider_driver_config
from src.drivers.registry import get_formalizer_driver, get_prover_driver
from src.explainer import explain_verification_result_async
from src.formalizer import formalize_claim
from src.lean import compile_check, lean_workspace_available
from src.models import (
    CompileRequest,
    CompileResponse,
    ErrorResponse,
    ExplainRequest,
    ExplainResponse,
    FormalizeRequest,
    FormalizeResponse,
    HealthResponse,
    JobStatus,
    MetricsResponse,
    SearchRequest,
    SearchResponse,
    VerifyAcceptedResponse,
    VerifyRequest,
)
from src.prover import VerificationHarness
from src.prover.file_controller import ProofFileController
from src.prover.tool_tracker import BudgetTracker
from src.search.engine import search_claim
from src.store import job_store

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


def _health_payload() -> HealthResponse:
    return HealthResponse(
        status="ok",
        lean_available=lean_workspace_available(),
        driver=DEFAULT_DRIVER,
        version=APP_VERSION,
    )


def _require_lean_toolchain() -> None:
    if not lean_workspace_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lean toolchain is not ready.",
        )


def _formalizer_driver():
    return get_formalizer_driver(
        DEFAULT_DRIVER,
        provider_driver_config(
            driver_name=DEFAULT_DRIVER,
            temperature=FORMALIZE_TEMPERATURE,
        ),
    )


def _prover_driver():
    return get_prover_driver(
        DEFAULT_DRIVER,
        provider_driver_config(
            driver_name=DEFAULT_DRIVER,
            temperature=PROVE_TEMPERATURE,
        ),
    )


def _verification_harness() -> VerificationHarness:
    return VerificationHarness(
        driver=_prover_driver(),
        file_controller=ProofFileController(),
        budget_tracker=BudgetTracker(),
    )


def _baseline_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    if not EVAL_CLAIMS_DIR.exists():
        return counts

    for path in sorted(EVAL_CLAIMS_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            counts[path.stem] = sum(1 for line in handle if line.strip())
    return counts


def _progress_log_line(stage: str, payload: dict[str, Any]) -> str:
    """Render a compact verification-progress line for console output."""

    parts = [f"stage={stage}"]
    for key in (
        "theorem",
        "step",
        "tactic",
        "success",
        "event_type",
        "tool_calls_made",
        "last_stage",
        "max_steps",
        "budget",
    ):
        value = payload.get(key)
        if value is not None:
            parts.append(f"{key}={value}")

    data = payload.get("data")
    if data is not None:
        parts.append(f"data={data}")

    return " | ".join(parts)


async def _run_verify_job(job_id: str, request: VerifyRequest) -> None:
    """Run one verification job to completion in the background."""

    harness = _verification_harness()
    last_stage = "init"
    print(
        f"[verify] {job_id}: started theorem={request.theorem_with_sorry.splitlines()[0]}",
        file=sys.stderr,
        flush=True,
    )

    def _progress_tracker(stage: str, payload: dict[str, Any]) -> None:
        nonlocal last_stage
        last_stage = stage
        job_store.record_progress(job_id, stage, payload=payload)
        print(
            f"[verify] {job_id}: {_progress_log_line(stage, payload)}",
            file=sys.stderr,
            flush=True,
        )

    def _partial_result(stop_reason: str) -> dict[str, Any]:
        """Build structured failure data from the harness's current state."""
        return {
            "partial": True,
            "stop_reason": stop_reason,
            "tool_calls_made": harness.budget_tracker.total_tool_calls,
            "last_stage": last_stage,
            "tool_history": list(harness.budget_tracker.tool_history),
            "tool_budget": harness.budget_tracker.snapshot(),
        }

    try:
        job_store.start(job_id)
        async with asyncio.timeout(request.timeout):
            status_result = await harness.verify(
                request.theorem_with_sorry,
                job_id,
                on_progress=_progress_tracker,
                max_steps=request.max_steps,
            )
        if status_result.status == "completed":
            job_store.complete(job_id, status_result.result or {})
            print(f"[verify] {job_id}: completed", file=sys.stderr, flush=True)
            return
        job_store.fail(
            job_id,
            status_result.error or "Verification failed.",
            result=status_result.result,
        )
        print(
            f"[verify] {job_id}: failed {status_result.error or 'Verification failed.'}",
            file=sys.stderr,
            flush=True,
        )
    except TimeoutError:
        job_store.fail(
            job_id,
            f"Verification timed out after {request.timeout}s.",
            result=_partial_result("timeout"),
        )
        print(
            f"[verify] {job_id}: failed Verification timed out after {request.timeout}s.",
            file=sys.stderr,
            flush=True,
        )
    except Exception as exc:
        job_store.fail(
            job_id,
            f"{exc.__class__.__name__}: {exc}",
            result=_partial_result("exception"),
        )
        print(
            f"[verify] {job_id}: failed {exc.__class__.__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )


@app.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def health() -> HealthResponse:
    """Return service health and Lean workspace readiness."""

    payload = _health_payload()
    if not payload.lean_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lean toolchain is not ready.",
        )
    return payload


@app.post(
    "/api/v2/search",
    response_model=SearchResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def search(request: SearchRequest) -> SearchResponse:
    """Run deterministic retrieval without calling any LLM provider."""

    try:
        return search_claim(request.raw_claim, request.domain)
    except Exception as exc:  # pragma: no cover - defensive deployment guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc.__class__.__name__}: {exc}",
        ) from exc


@app.post(
    "/api/v2/formalize",
    response_model=FormalizeResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def formalize(request: FormalizeRequest) -> FormalizeResponse:
    """Generate a compile-validated theorem stub."""

    search_context = search_claim(request.raw_claim).model_dump()
    return await formalize_claim(
        request.raw_claim,
        preamble_names=request.preamble_names,
        search_context=search_context,
    )


@app.post(
    "/api/v2/compile",
    response_model=CompileResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def compile_endpoint(request: CompileRequest) -> CompileResponse:
    """Compile Lean code directly with the local workspace toolchain."""

    _require_lean_toolchain()

    try:
        result = compile_check(request.lean_code)
    except Exception as exc:  # pragma: no cover - defensive deployment guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Compilation failed: {exc.__class__.__name__}: {exc}",
        ) from exc

    errors = list(result["errors"])
    if result["has_sorry"] and "Proof contains 'sorry'." not in errors:
        errors.append("Proof contains 'sorry'.")
    return CompileResponse(
        success=result["success"],
        output=result["output"],
        errors=errors,
    )


@app.post(
    "/api/v2/verify",
    response_model=VerifyAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def verify(request: VerifyRequest) -> VerifyAcceptedResponse:
    """Queue an asynchronous Lean proof attempt."""

    if "sorry" not in request.theorem_with_sorry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`theorem_with_sorry` must contain a `sorry` placeholder.",
        )

    job = job_store.create(request.model_dump())
    asyncio.create_task(_run_verify_job(job.id, request))
    return VerifyAcceptedResponse(
        job_id=job.id,
        status="queued",
        message="Verification job accepted.",
    )


@app.get("/api/v2/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    """Return the latest persisted job status."""

    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


@app.get("/api/v2/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    """Stream job progress as SSE events."""

    if job_store.get(job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    async def event_stream():
        subscriber = job_store.subscribe(job_id)
        try:
            snapshot = job_store.get(job_id)
            if snapshot is not None:
                yield f"data: {json.dumps({'type': 'snapshot', 'job': snapshot.model_dump()})}\n\n"
                if snapshot.status in {"completed", "failed"}:
                    return

            while True:
                try:
                    event = await asyncio.wait_for(subscriber.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue

                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") in {"completed", "failed"}:
                    return
        finally:
            job_store.unsubscribe(job_id, subscriber)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post(
    "/api/v2/explain",
    response_model=ExplainResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def explain(request: ExplainRequest) -> ExplainResponse:
    """Explain a verification result in natural language."""

    explanation = await explain_verification_result_async(request.verification_result)
    return ExplainResponse(explanation=explanation)


@app.get("/api/v2/metrics", response_model=MetricsResponse)
async def metrics() -> MetricsResponse:
    """Return benchmark and operational metrics."""

    counts = job_store.counts()
    baselines: dict[str, Any] = {
        "claim_sets": _baseline_counts(),
        "lean_available": lean_workspace_available(),
        "drivers": {
            "default": DEFAULT_DRIVER,
            "formalizer": _formalizer_driver().name,
            "prover": _prover_driver().name,
        },
    }
    return MetricsResponse(
        baselines=baselines,
        uptime=monotonic() - START_TIME,
        queue_depth=counts["queue_depth"],
        active_jobs=counts["active_jobs"],
    )
