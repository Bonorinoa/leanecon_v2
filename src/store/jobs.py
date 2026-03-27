"""SQLite-backed job store scaffold."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.config import DB_PATH
from src.models import JobStatus


class JobStore:
    """Minimal SQLite-backed persistence for job metadata."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path

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
                    error TEXT
                )
                """
            )
            connection.commit()

    def upsert(self, job: JobStatus) -> None:
        """Insert or replace a job record."""

        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO jobs (id, status, created_at, updated_at, result_json, error)
                VALUES (?, ?, ?, ?, ?, ?)
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

    def get(self, job_id: str) -> JobStatus | None:
        """Return a stored job when present."""

        if not self.db_path.exists():
            return None

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
