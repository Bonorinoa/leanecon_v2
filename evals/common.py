"""Shared helpers for in-process LeanEcon eval runs."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import httpx

from src.api import app
from src.config import CACHE_DIR, EVAL_CLAIMS_DIR

EVAL_OUTPUT_DIR = CACHE_DIR / "evals"


def claim_set_path(name: str) -> Path:
    """Resolve a claim-set name to a JSONL file path."""

    path = EVAL_CLAIMS_DIR / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Unknown claim set: {name}")
    return path


def load_claims(name: str) -> list[dict[str, Any]]:
    """Load one claim set from disk."""

    claims: list[dict[str, Any]] = []
    with claim_set_path(name).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            claims.append(json.loads(line))
    return claims


def make_client() -> httpx.AsyncClient:
    """Construct an ASGI-backed client against the local FastAPI app."""

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://leanecon.local")


def one_line(text: Any, *, limit: int = 100) -> str:
    """Normalize a value into one short console-friendly line."""

    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    if limit <= 3:
        return normalized[:limit]
    return normalized[: limit - 3].rstrip() + "..."


def claim_display_name(claim: dict[str, Any]) -> str:
    """Return a short label for one eval claim."""

    claim_id = claim.get("id")
    if claim_id:
        return one_line(claim_id, limit=80)

    theorem_stub = claim.get("theorem_stub") or claim.get("raw_lean") or claim.get("raw_claim")
    if theorem_stub:
        return one_line(str(theorem_stub).splitlines()[0], limit=80)
    return "unknown_claim"


def claim_prefix(
    runner_name: str,
    claim_index: int,
    total_claims: int,
    claim: dict[str, Any],
) -> str:
    """Build a consistent prefix for console progress output."""

    return f"[{runner_name} {claim_index}/{total_claims}] {claim_display_name(claim)}"


def log_line(message: str) -> None:
    """Emit one progress line immediately to stderr."""

    print(message, file=sys.stderr, flush=True)


def job_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the structured job result payload when present."""

    result = payload.get("result")
    if isinstance(result, dict):
        return result
    return {}


def job_progress_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the structured progress payload for one job poll response."""

    progress = job_result_payload(payload).get("progress")
    if isinstance(progress, dict):
        return progress
    return {}


def _job_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
    """Return a compact signature used to suppress duplicate job logs."""

    progress = job_progress_payload(payload)

    return (
        payload.get("status"),
        payload.get("error"),
        progress.get("stage"),
        progress.get("step"),
        progress.get("tactic"),
        progress.get("success"),
        progress.get("event_type"),
        progress.get("tool_calls_made"),
    )


def job_progress_line(payload: dict[str, Any]) -> str:
    """Render a job payload as a compact, readable status line."""

    parts = [f"status={one_line(payload.get('status', 'unknown'))}"]
    progress = job_progress_payload(payload)
    stage = progress.get("stage")
    if stage is not None:
        parts.append(f"stage={one_line(stage)}")
    for key in ("step", "tactic", "success", "event_type", "tool_calls_made", "data"):
        value = progress.get(key)
        if value is not None:
            parts.append(f"{key}={one_line(value)}")
    error = payload.get("error")
    if error:
        parts.append(f"error={one_line(error, limit=120)}")
    return " | ".join(parts)


async def poll_job(
    client: httpx.AsyncClient,
    job_id: str,
    *,
    timeout_seconds: float = 20.0,
    poll_interval: float = 0.2,
    heartbeat_seconds: float = 5.0,
    on_update: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Poll a queued verification job until it reaches a terminal state."""

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_signature: tuple[Any, ...] | None = None
    last_emit = 0.0
    while True:
        response = await client.get(f"/api/v2/jobs/{job_id}")
        response.raise_for_status()
        payload = response.json()

        now = asyncio.get_running_loop().time()
        signature = _job_signature(payload)
        if on_update is not None and (
            signature != last_signature
            or heartbeat_seconds <= 0
            or now - last_emit >= heartbeat_seconds
        ):
            if heartbeat_seconds > 0 and signature == last_signature:
                try:
                    on_update(payload, heartbeat=True)
                except TypeError:
                    on_update(payload)
            else:
                try:
                    on_update(payload, heartbeat=False)
                except TypeError:
                    on_update(payload)
            last_signature = signature
            last_emit = now

        if payload["status"] in {"completed", "failed"}:
            return payload
        if now >= deadline:
            raise TimeoutError(f"Timed out waiting for job {job_id}")
        await asyncio.sleep(poll_interval)


def _utc_now() -> str:
    """Return the current UTC timestamp for eval metadata."""

    return datetime.now(timezone.utc).isoformat()


def _percentile(values: list[float], percentile: float) -> float | None:
    """Compute a simple inclusive percentile for small eval samples."""

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = max(0.0, min(1.0, percentile)) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def summarize_latencies(latencies: list[float]) -> dict[str, float | int | None]:
    """Summarize latency samples for ratchet-friendly eval outputs."""

    return {
        "count": len(latencies),
        "mean": float(mean(latencies)) if latencies else None,
        "p50": _percentile(latencies, 0.50),
        "p95": _percentile(latencies, 0.95),
    }


def summarize_counts(values: list[int]) -> dict[str, float | int | None]:
    """Summarize integer counters such as attempt counts."""

    return {
        "count": len(values),
        "mean": float(mean(values)) if values else None,
        "max": max(values) if values else None,
    }


def frequency_table(values: list[str]) -> dict[str, int]:
    """Build a stable frequency table for string-valued measurements."""

    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _int_or_none(value: Any) -> int | None:
    """Return an integer value when the input can be losslessly normalized."""

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def extract_tool_budget(result: dict[str, Any]) -> dict[str, int | None]:
    """Normalize tool-budget data from one terminal verify result."""

    tool_budget = result.get("tool_budget")
    if not isinstance(tool_budget, dict):
        tool_budget = {}

    tool_history = result.get("tool_history")
    tool_history_count = len(tool_history) if isinstance(tool_history, list) else None
    total_tool_calls = (
        _int_or_none(result.get("tool_calls_made"))
        or _int_or_none(tool_budget.get("total_tool_calls"))
        or tool_history_count
    )

    return {
        "tool_calls_made": total_tool_calls,
        "max_total_tool_calls": _int_or_none(tool_budget.get("max_total_tool_calls")),
        "max_search_tool_calls": _int_or_none(tool_budget.get("max_search_tool_calls")),
        "search_tool_calls": _int_or_none(tool_budget.get("search_tool_calls")),
    }


def classify_job_error(status: str, result: dict[str, Any]) -> str | None:
    """Map heterogeneous job failures into stable dashboard error buckets."""

    stop_reason = result.get("stop_reason")
    if stop_reason == "timeout":
        return "timeout"
    if stop_reason == "exception":
        return "exception"
    if status == "skipped":
        return "skipped"
    if status != "failed":
        return None

    compile_payload = result.get("compile")
    if isinstance(compile_payload, dict) and compile_payload.get("errors"):
        return "compile_error"
    return "verification_failed"


def summarize_tool_budget(
    tool_calls_made: list[int],
    *,
    max_total_tool_calls: int | None,
    max_search_tool_calls: int | None,
) -> dict[str, float | int | None]:
    """Summarize tool-budget usage for one eval run."""

    return {
        "max_total_tool_calls": max_total_tool_calls,
        "max_search_tool_calls": max_search_tool_calls,
        "mean_tool_calls_made": float(mean(tool_calls_made)) if tool_calls_made else None,
        "max_tool_calls_made": max(tool_calls_made) if tool_calls_made else None,
    }


def default_output_path(runner_name: str, claim_set: str) -> Path:
    """Return the default JSON artifact path for one eval runner."""

    return EVAL_OUTPUT_DIR / f"{runner_name}_{claim_set}.json"


def write_summary(
    runner_name: str,
    claim_set: str,
    summary: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    """Persist one eval summary as machine-readable JSON."""

    path = output_path or default_output_path(runner_name, claim_set)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "runner": runner_name,
        "claim_set": claim_set,
        "generated_at": _utc_now(),
        **summary,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
