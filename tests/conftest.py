"""Pytest fixtures for LeanEcon v2."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import app


@pytest.fixture()
def client() -> TestClient:
    """Return a FastAPI test client."""

    return TestClient(app)
