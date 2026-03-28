"""Shared helpers for in-process LeanEcon eval runs."""

from __future__ import annotations

import asyncio
import json
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


async def poll_job(
    client: httpx.AsyncClient,
    job_id: str,
    *,
    timeout_seconds: float = 20.0,
    poll_interval: float = 0.2,
) -> dict[str, Any]:
    """Poll a queued verification job until it reaches a terminal state."""

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        response = await client.get(f"/api/v2/jobs/{job_id}")
        response.raise_for_status()
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        if asyncio.get_running_loop().time() >= deadline:
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
