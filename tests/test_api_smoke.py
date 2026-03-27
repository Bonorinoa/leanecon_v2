"""API smoke tests for the Phase 3 implementation."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_health_endpoint_reports_runtime_status(client: TestClient) -> None:
    """The health endpoint should expose liveness and Lean readiness."""

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["driver"] == "mistral"
    assert payload["version"] == "2.0.0-alpha"
    assert isinstance(payload["lean_available"], bool)


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
    assert payload["candidate_imports"]
    assert payload["candidate_identifiers"]
    assert payload["curated_hints"]


def test_compile_endpoint_compiles_simple_theorem_stub(client: TestClient) -> None:
    """The compile endpoint should run the local Lean compiler."""

    response = client.post(
        "/api/v2/compile",
        json={"lean_code": "theorem two_eq_two : 2 = 2 := by\n  sorry\n"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "Proof contains 'sorry'." in payload["errors"]


def test_verify_endpoint_runs_job_to_completion(client: TestClient) -> None:
    """Verification jobs should queue, transition, and persist terminal results."""

    theorem_with_sorry = (
        "theorem benchmark_one_plus_one : 1 + 1 = 2 := by\n"
        "  sorry\n"
    )
    response = client.post(
        "/api/v2/verify",
        json={"theorem_with_sorry": theorem_with_sorry},
    )

    assert response.status_code == 202
    payload = response.json()
    job_id = payload["job_id"]

    for _ in range(100):
        poll = client.get(f"/api/v2/jobs/{job_id}")
        assert poll.status_code == 200
        terminal = poll.json()
        if terminal["status"] in {"completed", "failed"}:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("verification job did not reach a terminal state")

    assert terminal["status"] == "completed"
    assert terminal["result"]["status"] == "verified"


def test_metrics_endpoint_is_live(client: TestClient) -> None:
    """Metrics should expose baseline counts and queue information."""

    response = client.get("/api/v2/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert "claim_sets" in payload["baselines"]
    assert "tier0_smoke" in payload["baselines"]["claim_sets"]
