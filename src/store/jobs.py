"""SQLite-backed job store with in-memory SSE subscribers."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import DB_PATH, JOB_TTL_SECONDS
from src.models import JobStatus


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """SQLite-backed persistence plus in-process pub/sub for SSE."""

    def __init__(self, db_path: Path = DB_PATH, ttl_seconds: int = JOB_TTL_SECONDS) -> None:
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self.initialize()

    def initialize(self) -> None:
        """Create the jobs table when it does not already exist."""

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    request_json TEXT
                )
                """
            )
            connection.commit()

    def _cleanup_expired(self) -> None:
        """Purge expired rows and their subscriber queues."""

        if not self.db_path.exists():
            return

        cutoff = time.time() - self.ttl_seconds
        expired: list[str] = []
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute("SELECT id, created_at FROM jobs").fetchall()
            for job_id, created_at in rows:
                try:
                    created_ts = datetime.fromisoformat(created_at).timestamp()
                except ValueError:
                    continue
                if created_ts < cutoff:
                    expired.append(job_id)

            for job_id in expired:
                connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            connection.commit()

        for job_id in expired:
            self._subscribers.pop(job_id, None)

    def upsert(self, job: JobStatus) -> None:
        """Insert or replace a job record."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, status, created_at, updated_at, result_json, error, request_json
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    result_json = excluded.result_json,
                    error = excluded.error
                """,
                (
                    job.id,
                    job.status,
                    job.created_at,
                    job.updated_at,
                    json.dumps(job.result) if job.result is not None else None,
                    job.error,
                ),
            )
            connection.commit()

    def create(self, request_data: dict[str, Any] | None = None) -> JobStatus:
        """Create and persist a queued job record."""

        created_at = _utc_now()
        job = JobStatus(
            id=str(uuid.uuid4()),
            status="queued",
            created_at=created_at,
            updated_at=created_at,
            result={"request": request_data} if request_data else None,
            error=None,
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, status, created_at, updated_at, result_json, error, request_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.status,
                    job.created_at,
                    job.updated_at,
                    json.dumps(job.result) if job.result is not None else None,
                    None,
                    json.dumps(request_data) if request_data is not None else None,
                ),
            )
            connection.commit()
        return job

    def start(self, job_id: str) -> JobStatus | None:
        """Mark a queued job as running."""

        job = self.get(job_id)
        if job is None:
            return None

        job.status = "running"
        job.updated_at = _utc_now()
        self.upsert(job)
        self.publish(job_id, {"type": "start", "status": "running", "job_id": job_id})
        return job

    def record_progress(
        self,
        job_id: str,
        stage: str,
        *,
        status: str = "running",
        payload: dict[str, Any] | None = None,
    ) -> JobStatus | None:
        """Persist a progress snapshot and publish an SSE event."""

        job = self.get(job_id)
        if job is None:
            return None

        snapshot = dict(job.result or {})
        progress = dict(snapshot.get("progress", {}))
        progress.update({"stage": stage, "status": status})
        if payload:
            progress.update(payload)
        snapshot["progress"] = progress

        job.status = status
        job.updated_at = _utc_now()
        job.result = snapshot
        self.upsert(job)
        self.publish(
            job_id,
            {
                "type": "progress",
                "status": status,
                "stage": stage,
                "job_id": job_id,
                "payload": payload or {},
            },
        )
        return job

    def complete(self, job_id: str, result: dict[str, Any]) -> JobStatus | None:
        """Mark a job completed and publish a terminal event."""

        job = self.get(job_id)
        if job is None:
            return None

        job.status = "completed"
        job.updated_at = _utc_now()
        job.result = result
        job.error = None
        self.upsert(job)
        self.publish(job_id, {"type": "complete", "status": "completed", "job_id": job_id})
        return job

    def fail(
        self,
        job_id: str,
        error: str,
        result: dict[str, Any] | None = None,
    ) -> JobStatus | None:
        """Mark a job failed and publish a terminal event."""

        job = self.get(job_id)
        if job is None:
            return None

        job.status = "failed"
        job.updated_at = _utc_now()
        job.result = result
        job.error = error
        self.upsert(job)
        event: dict[str, Any] = {
            "type": "complete",
            "status": "failed",
            "job_id": job_id,
            "error": error,
        }
        if result is not None:
            event["result"] = result
        self.publish(job_id, event)
        return job

    def get(self, job_id: str) -> JobStatus | None:
        """Return a stored job when present."""

        if not self.db_path.exists():
            return None

        self._cleanup_expired()
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, status, created_at, updated_at, result_json, error
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            return None

        result_json = json.loads(row[4]) if row[4] else None
        return JobStatus(
            id=row[0],
            status=row[1],
            created_at=row[2],
            updated_at=row[3],
            result=result_json,
            error=row[5],
        )

    def subscribe(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Create an SSE subscriber queue for a job."""

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(queue)
        return queue

    def unsubscribe(self, job_id: str, subscriber: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove an SSE subscriber queue."""

        with self._lock:
            subscribers = self._subscribers.get(job_id, [])
            if subscriber in subscribers:
                subscribers.remove(subscriber)
            if not subscribers and job_id in self._subscribers:
                del self._subscribers[job_id]

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        """Publish an event to all active SSE subscribers."""

        with self._lock:
            subscribers = list(self._subscribers.get(job_id, []))

        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except asyncio.QueueFull:
                continue

    def counts(self) -> dict[str, int]:
        """Return queue depth and active-job counts for metrics."""

        self._cleanup_expired()
        if not self.db_path.exists():
            return {"queue_depth": 0, "active_jobs": 0}

        with sqlite3.connect(self.db_path) as connection:
            queued = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'queued'"
            ).fetchone()[0]
            running = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'running'"
            ).fetchone()[0]
        return {"queue_depth": int(queued), "active_jobs": int(running)}


job_store = JobStore()
