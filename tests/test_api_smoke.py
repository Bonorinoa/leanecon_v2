"""API smoke tests for the Phase 3 implementation."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_health_endpoint_reports_runtime_status(client: TestClient, monkeypatch) -> None:
    """The health endpoint should expose liveness and Lean readiness."""

    monkeypatch.setattr("src.api.lean_workspace_available", lambda: True)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["driver"] == "mistral"
    assert payload["version"] == "2.0.0-alpha"
    assert isinstance(payload["lean_available"], bool)


def test_health_endpoint_returns_service_unavailable_when_lean_is_missing(
    client: TestClient,
    monkeypatch,
) -> None:
    """Health should fail closed when the lake probe is unavailable."""

    monkeypatch.setattr("src.api.lean_workspace_available", lambda: False)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"] == "Lean toolchain is not ready."


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


def test_search_endpoint_surfaces_internal_errors_as_http_500(
    client: TestClient,
    monkeypatch,
) -> None:
    """Search should convert unexpected failures into a clean API error."""

    def boom(*args, **kwargs):
        _ = args
        _ = kwargs
        raise RuntimeError("search exploded")

    monkeypatch.setattr("src.api.search_claim", boom)

    response = client.post(
        "/api/v2/search",
        json={"raw_claim": "Every competitive equilibrium is Pareto efficient."},
    )

    assert response.status_code == 500
    assert "Search failed:" in response.json()["detail"]


def test_compile_endpoint_compiles_simple_theorem_stub(
    client: TestClient,
    monkeypatch,
) -> None:
    """The compile endpoint should run the local Lean compiler."""

    monkeypatch.setattr("src.api.lean_workspace_available", lambda: True)

    def fake_compile_check(lean_code: str, *, timeout=None, filename=None, check_axioms=False):
        _ = lean_code
        _ = timeout
        _ = filename
        _ = check_axioms
        return {
            "success": True,
            "has_sorry": False,
            "axiom_warnings": [],
            "output": "compiled",
            "errors": [],
            "warnings": [],
            "stdout": "compiled",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr("src.api.compile_check", fake_compile_check)

    response = client.post(
        "/api/v2/compile",
        json={"lean_code": "theorem two_eq_two : 2 = 2 := by\n  trivial\n"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["output"] == "compiled"
    assert payload["errors"] == []


def test_compile_endpoint_returns_service_unavailable_when_lean_is_missing(
    client: TestClient,
    monkeypatch,
) -> None:
    """Compile should fail closed when the lake probe is unavailable."""

    monkeypatch.setattr("src.api.lean_workspace_available", lambda: False)

    response = client.post(
        "/api/v2/compile",
        json={"lean_code": "theorem two_eq_two : 2 = 2 := by\n  trivial\n"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Lean toolchain is not ready."


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
