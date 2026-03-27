# Architecture

LeanEcon v2 is organized around a narrow, explicit API contract and a
three-layer trust model:

1. Stochastic formalization and proving.
2. Human review of theorem stubs.
3. Deterministic Lean kernel verification.

## Core Subsystems

- `src/api.py` exposes the public FastAPI surface.
- `src/search` provides deterministic retrieval, curated hints, and domain
  tagging.
- `src/formalizer` owns theorem-stub generation and scope checks.
- `src/prover` orchestrates provider-backed proving without embedding provider
  logic directly.
- `src/drivers` contains provider adapters behind stable protocols.
- `src/lean` wraps local Lean compile and validation primitives.
- `src/store` persists jobs and cached artifacts.
- `src/explainer` turns verification results into plain-language summaries.

## Phase 2A Boundaries

- `/health` and `/api/v2/search` are implemented.
- Other routes are present to lock the contract but explicitly deferred.
- The Lean workspace is a placeholder until Phase 2B copies in trusted assets.
