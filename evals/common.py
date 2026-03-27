"""Shared helpers for in-process LeanEcon eval runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from src.api import app
from src.config import EVAL_CLAIMS_DIR


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
