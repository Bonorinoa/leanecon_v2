"""API smoke tests for the Phase 2A scaffold."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint_returns_alpha_status(client: TestClient) -> None:
    """The health endpoint should report liveness without Lean readiness."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "lean_available": False,
        "driver": "mistral",
        "version": "2.0.0-alpha",
    }


def test_search_endpoint_accepts_claim_and_returns_deterministic_shape(
    client: TestClient,
) -> None:
    """The search endpoint should return advisory retrieval data."""

    response = client.post(
        "/api/v2/search",
        json={"raw_claim": "Every competitive equilibrium is Pareto efficient."},
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["domain"] == "economics"
    assert payload["preamble_matches"] == []
    assert payload["candidate_imports"]
    assert payload["candidate_identifiers"]
    assert payload["curated_hints"]
