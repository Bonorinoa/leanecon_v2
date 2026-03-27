"""Pytest fixtures for LeanEcon v2."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import app
from src.store.jobs import job_store


@pytest.fixture(autouse=True)
def isolated_job_store(tmp_path: Path) -> None:
    """Reset the singleton job store to a temporary database for each test."""

    job_store.db_path = tmp_path / "jobs.db"
    job_store._subscribers.clear()
    job_store.initialize()


@pytest.fixture()
def anyio_backend() -> str:
    """Run async tests on asyncio only."""

    return "asyncio"


@pytest.fixture()
def client() -> TestClient:
    """Return a FastAPI test client."""

    return TestClient(app)
