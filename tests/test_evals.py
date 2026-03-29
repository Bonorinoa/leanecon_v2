"""Eval helper tests for artifact generation."""

from __future__ import annotations

import json

import pytest

from evals.common import (
    classify_job_error,
    extract_tool_budget,
    job_progress_line,
    poll_job,
    summarize_latencies,
    summarize_tool_budget,
    write_summary,
)


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


def test_write_summary_preserves_dashboard_metadata_fields(tmp_path) -> None:
    """Additive dashboard metadata should survive artifact serialization unchanged."""

    output_path = tmp_path / "prover.json"
    artifact_path = write_summary(
        "prover_only",
        "agentic_harness",
        {
            "pass_at_1": 0.7,
            "total_claims": 10,
            "tool_budget": {
                "max_total_tool_calls": 40,
                "max_search_tool_calls": 8,
                "mean_tool_calls_made": 6.5,
                "max_tool_calls_made": 12,
            },
            "cases": [
                {
                    "id": "ag_case_1",
                    "status": "failed",
                    "error_type": "timeout",
                    "error_message": "Verification timed out after 300s.",
                    "last_stage": "provider",
                    "tool_calls_made": 12,
                    "max_tool_calls": 40,
                    "max_search_tool_calls": 8,
                    "stop_reason": "timeout",
                }
            ],
        },
        output_path=output_path,
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["runner"] == "prover_only"
    assert payload["pass_at_1"] == 0.7
    assert payload["tool_budget"]["max_total_tool_calls"] == 40
    assert payload["cases"][0]["error_type"] == "timeout"
    assert payload["cases"][0]["last_stage"] == "provider"


def test_extract_tool_budget_reads_snapshot_fields() -> None:
    """Tool-budget extraction should normalize the snapshot shape used by verify jobs."""

    budget = extract_tool_budget(
        {
            "tool_budget": {
                "max_total_tool_calls": 40,
                "max_search_tool_calls": 8,
                "search_tool_calls": 2,
                "total_tool_calls": 5,
            },
            "tool_history": ["search", "compile_current_code", "apply_tactic"],
        }
    )

    assert budget["tool_calls_made"] == 5
    assert budget["max_total_tool_calls"] == 40
    assert budget["max_search_tool_calls"] == 8
    assert budget["search_tool_calls"] == 2


def test_classify_job_error_normalizes_failure_modes() -> None:
    """Dashboard error buckets should be stable across timeout and compile failures."""

    assert classify_job_error("failed", {"stop_reason": "timeout"}) == "timeout"
    assert classify_job_error("failed", {"stop_reason": "exception"}) == "exception"
    assert (
        classify_job_error("failed", {"compile": {"errors": ["unsolved goals"]}})
        == "compile_error"
    )
    assert classify_job_error("failed", {}) == "verification_failed"
    assert classify_job_error("skipped", {}) == "skipped"
    assert classify_job_error("completed", {}) is None


def test_summarize_tool_budget_returns_dashboard_fields() -> None:
    """Run-level tool budget summaries should expose stable dashboard keys."""

    summary = summarize_tool_budget(
        [4, 6, 10],
        max_total_tool_calls=40,
        max_search_tool_calls=8,
    )

    assert summary["max_total_tool_calls"] == 40
    assert summary["max_search_tool_calls"] == 8
    assert summary["mean_tool_calls_made"] == pytest.approx(20 / 3)
    assert summary["max_tool_calls_made"] == 10


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
