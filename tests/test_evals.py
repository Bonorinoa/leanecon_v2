"""Eval helper tests for artifact generation."""

from __future__ import annotations

import json

import pytest

from evals.common import job_progress_line, poll_job, summarize_latencies, write_summary


def test_summarize_latencies_returns_percentiles() -> None:
    """Latency summaries should expose stable percentile fields."""

    summary = summarize_latencies([1.0, 2.0, 3.0, 4.0])

    assert summary["count"] == 4
    assert summary["mean"] == 2.5
    assert summary["p50"] == 2.5
    assert summary["p95"] == 3.8499999999999996


def test_write_summary_persists_json_artifact(tmp_path) -> None:
    """Eval summaries should be written as machine-readable JSON."""

    output_path = tmp_path / "formalizer.json"
    artifact_path = write_summary(
        "formalizer_only",
        "tier0_smoke",
        {"pass_at_1": 1.0, "total_claims": 3},
        output_path=output_path,
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_path == output_path
    assert payload["runner"] == "formalizer_only"
    assert payload["claim_set"] == "tier0_smoke"
    assert payload["pass_at_1"] == 1.0


@pytest.mark.anyio
async def test_poll_job_emits_progress_updates() -> None:
    """Polling should surface job progress transitions to the caller."""

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self) -> None:
            self._responses = [
                {"status": "queued", "result": {"progress": {"stage": "initialize"}}},
                {
                    "status": "running",
                    "result": {
                        "progress": {
                            "stage": "fast_path",
                            "step": 1,
                            "tactic": "simp",
                            "success": False,
                        }
                    },
                },
                {"status": "completed", "result": {"status": "verified"}},
            ]

        async def get(self, _path: str) -> FakeResponse:
            payload = self._responses.pop(0)
            return FakeResponse(payload)

    updates: list[str] = []

    terminal = await poll_job(
        FakeClient(),
        "job_1",
        timeout_seconds=1.0,
        poll_interval=0.0,
        heartbeat_seconds=999.0,
        on_update=lambda payload, heartbeat=False: updates.append(
            f"{job_progress_line(payload)}|heartbeat={heartbeat}"
        ),
    )

    assert terminal["status"] == "completed"
    assert updates[0].startswith("status=queued")
    assert "stage=fast_path" in updates[1]
    assert updates[-1].startswith("status=completed")
