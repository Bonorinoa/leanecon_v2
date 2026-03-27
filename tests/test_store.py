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
