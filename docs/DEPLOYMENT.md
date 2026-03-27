# Deployment

## Target

Phase 2A is set up for container deployment on Railway with a single FastAPI
service and a future Lean workspace mounted in-repo.

## Container Notes

- The Docker image uses `python:3.11-slim`.
- `elan` is installed so Lean toolchains can be added in later phases.
- The app starts with `uvicorn src.api:app`.

## Environment

At minimum, set:

- `PORT`
- `LEANECON_DRIVER`
- `MISTRAL_API_KEY` when provider-backed proving is enabled
- `HF_TOKEN` for Hugging Face ecosystem interactions

## Phase 2A Caveat

Lean toolchain and workspace readiness are intentionally deferred. The health
endpoint reports the alpha scaffold state rather than claiming full Lean
availability.
