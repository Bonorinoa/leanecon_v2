# Deployment

## Target

Phase 2.4 is set up for container deployment on Railway with a single FastAPI
service and the in-repo Lean workspace built into the image.

## Container Notes

- The Docker image uses `python:3.11-slim`.
- `elan` installs the Lean toolchain pinned by `lean_workspace/lean-toolchain`.
- The image runs `lake update` and `lake build LeanEcon` during build so the
	Lean workspace is ready before the API starts.
- The app starts with `uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}`.

## Environment

At minimum, set:

- `PORT`
- `LEANECON_DRIVER`
- `MISTRAL_API_KEY` when provider-backed proving is enabled
- `HF_TOKEN` for Hugging Face ecosystem interactions

## Phase 2.4 Caveat

The health endpoint now fails closed if the Lean workspace cannot be probed,
including the `lake` executable check. This makes Railway readiness reflect the
actual container state instead of a filesystem-only approximation.
