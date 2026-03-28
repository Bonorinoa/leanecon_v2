"""Store tests for the Phase 2A scaffold."""

from __future__ import annotations

from datetime import datetime, timezone

from src.models import JobStatus
from src.store.jobs import JobStore


def test_job_store_round_trip(tmp_path) -> None:
    """The SQLite-backed scaffold should persist and load job metadata."""

    store = JobStore(db_path=tmp_path / "jobs.db")
    now = datetime.now(timezone.utc).isoformat()
    job = JobStatus(
        id="job_1",
        status="queued",
        created_at=now,
        updated_at=now,
        result=None,
        error=None,
    )

    store.upsert(job)
    loaded = store.get("job_1")

    assert loaded is not None
    assert loaded.id == "job_1"
    assert loaded.status == "queued"


def test_job_store_lifecycle_and_counts(tmp_path) -> None:
    """The expanded job store should support lifecycle helpers and queue counts."""

    store = JobStore(db_path=tmp_path / "jobs.db")
    job = store.create({"kind": "verify"})
    counts = store.counts()
    assert counts["queue_depth"] == 1

    store.start(job.id)
    store.record_progress(job.id, "fast_path", payload={"step": 1})
    running = store.get(job.id)
    assert running is not None
    assert running.status == "running"
    assert running.result is not None
    assert running.result["progress"]["stage"] == "fast_path"

    store.complete(job.id, {"status": "verified"})
    finished = store.get(job.id)
    assert finished is not None
    assert finished.status == "completed"


def test_job_store_fail_with_structured_result(tmp_path) -> None:
    """Failing a job with a result dict should persist and publish structured data."""

    import asyncio

    store = JobStore(db_path=tmp_path / "jobs.db")
    job = store.create({"kind": "verify"})
    store.start(job.id)

    subscriber = store.subscribe(job.id)

    partial_result = {
        "partial": True,
        "stop_reason": "timeout",
        "tool_calls_made": 5,
        "last_stage": "provider",
        "tool_history": ["read_current_code", "compile_current_code", "apply_tactic"],
    }
    store.fail(job.id, "Verification timed out after 300s.", result=partial_result)

    failed = store.get(job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "Verification timed out after 300s."
    assert failed.result is not None
    assert failed.result["partial"] is True
    assert failed.result["stop_reason"] == "timeout"
    assert failed.result["tool_calls_made"] == 5

    # The SSE event should include the result
    event = subscriber.get_nowait()
    assert event["type"] == "complete"
    assert event["status"] == "failed"
    assert "result" in event
    assert event["result"]["partial"] is True
    assert event["result"]["stop_reason"] == "timeout"
