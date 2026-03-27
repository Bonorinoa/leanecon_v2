"""Store tests for the Phase 2A scaffold."""

from __future__ import annotations

from src.models import JobStatus
from src.store.jobs import JobStore


def test_job_store_round_trip(tmp_path) -> None:
    """The SQLite-backed scaffold should persist and load job metadata."""

    store = JobStore(db_path=tmp_path / "jobs.db")
    job = JobStatus(
        id="job_1",
        status="queued",
        created_at="2026-03-26T00:00:00Z",
        updated_at="2026-03-26T00:00:00Z",
        result=None,
        error=None,
    )

    store.upsert(job)
    loaded = store.get("job_1")

    assert loaded is not None
    assert loaded.id == "job_1"
    assert loaded.status == "queued"
