"""Eval helper tests for artifact generation."""

from __future__ import annotations

import json

from evals.common import summarize_latencies, write_summary


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
