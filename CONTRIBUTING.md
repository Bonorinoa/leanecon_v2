# Contributing

LeanEcon v2 favors small, explicit changes that preserve the public API
contract and keep the deterministic Lean boundary easy to audit. The repo is
backend-only; frontend clients should live outside this codebase and consume the
published API directly.

## Local Validation

Run the core checks before opening a pull request:

```bash
./.venv/bin/python -c "from src.config import PROJECT_ROOT; print(PROJECT_ROOT)"
./.venv/bin/python -m pytest
./.venv/bin/ruff check src tests evals
```

## What Makes a Good Change

- Keep route handlers thin and move behavior into modules.
- Preserve provider-agnostic interfaces in `src/drivers`.
- Treat retrieval hints and prompts as research surfaces, not silent behavior.
- Prefer deterministic fallbacks over hidden LLM coupling.
- Add or update tests when behavior changes.

## Documentation Rules

- Update `docs/API_CONTRACT.md` when request or response shapes change.
- Update `PROGRAM.md` only with explicit human approval.
- Keep architecture and deployment docs aligned with the actual scaffold.
