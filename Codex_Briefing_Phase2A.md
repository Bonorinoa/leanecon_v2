# LeanEcon v2 — Codex Briefing

**Date:** March 26, 2026
**Context:** You are Codex 5.4 in VSCode, working on a freshly cloned empty repository at `https://github.com/Bonorinoa/leanecon_v2`. Your job is to scaffold the v2 repository structure, write the steering documents, and prepare the foundation for a provider-agnostic formal verification API.

**Do NOT clone or reference the v1 repository directly.** The Lean workspace and claim sets will be copied separately (Phase 2B). Focus only on creating the scaffold, documents, and Python source skeletons.

---

## What LeanEcon Is

LeanEcon is a formal verification API for mathematical claims in economics. It takes claims in natural language, LaTeX, or raw Lean 4, translates them into machine-checkable theorems, generates proofs using an agentic LLM prover (Leanstral), and verifies them against Lean 4's kernel. Three-layer trust model:

1. **Stochastic layer** — LLM generates candidate formalizations and proofs. May fail.
2. **Human-in-the-loop** — User reviews formalized theorem before proving.
3. **Deterministic layer** — Lean 4 kernel verifies the proof from axioms. If it passes, it's mathematically certified.

## V2 Design Principles

1. **Simplification over features.** V1's bottleneck is complexity, not capability.
2. **Provider-agnostic.** The prover harness does not know which LLM is behind it.
3. **Autoresearch-compatible.** The repo structure supports Karpathy-style ratchet loops on the stochastic layers.
4. **Explicit over implicit.** No endpoint silently does work that belongs to another endpoint.
5. **HuggingFace as ecosystem layer.** Datasets, model registry, eval artifacts. Not the runtime (yet).

## V2 API Contract (Final — do not modify)

| Endpoint | Method | Purpose | Type |
|----------|--------|---------|------|
| `/health` | GET | Liveness + Lean environment status | Sync |
| `/api/v2/search` | POST | Preamble matching, curated hints, Mathlib concept lookup, domain tagging. **No LLM call.** Deterministic retrieval only. | Sync |
| `/api/v2/formalize` | POST | Produce Lean theorem stub with sorry. Includes scope check. Calls search internally. Returns scope advisory + retrieval context in response. | Sync |
| `/api/v2/compile` | POST | Direct Lean compile check (debug primitive). Synchronous, local-only. | Sync |
| `/api/v2/verify` | POST | Queue agentic proof generation + kernel check. Returns 202 + job_id. | Async |
| `/api/v2/jobs/{id}` | GET | Poll job status and result. | Sync |
| `/api/v2/jobs/{id}/stream` | GET | SSE progress events. | Streaming |
| `/api/v2/explain` | POST | Natural language explanation of verification result. | Sync |
| `/api/v2/metrics` | GET | Benchmark snapshot and system telemetry. Read-only. | Sync |

### Key contract rules:
- `/verify` does exactly one thing: prove the supplied theorem. It does NOT classify, formalize, or retrieve context.
- `/search` is deterministic — no LLM calls. It searches preamble entries, curated hints, and optionally Mathlib concepts.
- `/formalize` calls `/search` logic internally but also makes an LLM call for statement generation. The response includes both the theorem stub and the retrieval context used.
- All retrieval context is advisory data. It never silently influences `/verify`.

---

## Task List

### Task 1: Create Directory Structure

Create the following structure in the repo root:

```
leanecon-v2/
├── PROGRAM.md
├── ROADMAP.md
├── README.md
├── LICENSE                       # Apache-2.0 (already created)
├── NOTICE
├── CONTRIBUTING.md
├── TRADEMARK.md
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API_CONTRACT.md
│   ├── DEPLOYMENT.md
│   ├── PAPER.md
│   └── PROVIDER_GUIDE.md
│
├── src/
│   ├── __init__.py
│   ├── api.py
│   ├── config.py
│   ├── models.py
│   │
│   ├── search/
│   │   ├── __init__.py
│   │   ├── engine.py             # Preamble matching, curated hints, domain tagging
│   │   └── hints.py              # Curated hint definitions (autoresearchable)
│   │
│   ├── formalizer/
│   │   ├── __init__.py
│   │   ├── formalizer.py         # Statement shaping logic
│   │   └── prompts.py            # Formalizer prompt templates (autoresearchable)
│   │
│   ├── prover/
│   │   ├── __init__.py
│   │   ├── harness.py            # Provider-agnostic proving orchestration
│   │   ├── file_controller.py    # Proof file management, checkpoints
│   │   ├── tool_tracker.py       # Budget enforcement, circuit breakers
│   │   ├── fast_path.py          # Local tactic fast path (autoresearchable)
│   │   └── prompts.py            # Prover instructions (autoresearchable)
│   │
│   ├── drivers/
│   │   ├── __init__.py
│   │   ├── base.py               # ProverDriver protocol (abstract)
│   │   ├── mistral.py            # Mistral Conversations API adapter
│   │   └── registry.py           # Driver discovery and selection
│   │
│   ├── lean/
│   │   ├── __init__.py
│   │   ├── compiler.py           # lean_run_code, lake build wrappers
│   │   └── validators.py         # Sorry detection, axiom checking
│   │
│   ├── store/
│   │   ├── __init__.py
│   │   ├── jobs.py               # Job store (SQLite-backed)
│   │   └── cache.py              # Result cache (file-backed JSON)
│   │
│   └── explainer/
│       ├── __init__.py
│       └── explainer.py
│
├── lean_workspace/               # (placeholder — will be populated from v1)
│   └── .gitkeep
│
├── evals/
│   ├── __init__.py
│   ├── claim_sets/
│   │   ├── tier1_core.jsonl      # (placeholder — will be populated from v1)
│   │   ├── tier2_frontier.jsonl
│   │   └── out_of_scope.jsonl
│   ├── formalizer_only.py
│   ├── prover_only.py
│   ├── e2e.py
│   └── report.py
│
├── skills/
│   ├── SKILL_LEAN.md             # (placeholder — will be copied from v1)
│   └── leanecon-api-SKILL.md     # (placeholder — will be updated for v2)
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_api_smoke.py
    ├── test_search.py
    ├── test_formalizer.py
    ├── test_prover.py
    └── test_store.py
```

### Task 2: Write PROGRAM.md

This is the Karpathy-style autoresearch steering file. Write it with the following content:

```markdown
# PROGRAM.md — LeanEcon v2 Autoresearch Steering

## Mission

LeanEcon v2 formally verifies mathematical economics claims using Lean 4.
Agents optimize the stochastic layers (formalization and proving) while the
deterministic layer (Lean kernel) and the API contract remain human-controlled.

## Autoresearch Loops

### Loop 1 — Formalizer Ratchet

**Goal:** Improve the system's ability to turn natural-language economics claims
into compilable Lean 4 theorem stubs.

**Editable zone:**
- `src/formalizer/prompts.py` — prompt templates and few-shot examples
- `src/search/hints.py` — curated hint definitions, keyword-to-import mappings
- Retrieval tuning parameters in `src/search/engine.py`

**Scoring function:** `python evals/formalizer_only.py`
- Reads `evals/claim_sets/tier1_core.jsonl`
- Calls formalize on each claim
- Runs `lean_run_code` on returned theorem stub
- Outputs: pass@1, semantic score distribution, latency p50/p95

**Time budget:** 5 minutes per experiment.

**Ratchet rule:** Keep if pass@1 strictly improves, OR if pass@1 is equal and
semantic score average improves. Discard otherwise.

### Loop 2 — Prover Ratchet

**Goal:** Improve the system's ability to prove well-formed Lean 4 theorem stubs.

**Editable zone:**
- `src/prover/prompts.py` — prover instructions and system prompt
- `src/prover/fast_path.py` — local tactic shortcuts
- Budget parameters in `src/prover/tool_tracker.py`

**Scoring function:** `python evals/prover_only.py`
- Reads a fixed set of pre-formalized theorem stubs
- Calls verify on each
- Outputs: pass@1, latency p50/p95, tool call distribution

**Time budget:** 10 minutes per experiment.

**Ratchet rule:** Keep if pass@1 strictly improves, OR if pass@1 is equal and
latency p50 decreases by ≥10%. Discard otherwise.

## Off-Limits Zones (require human PR approval)

These files must NOT be modified by autoresearch agents without explicit
human review and merge:

- `lean_workspace/` — all Lean source files and preamble definitions
- `src/api.py` — endpoint routing and signatures
- `src/models.py` — request/response Pydantic schemas
- `src/drivers/base.py` — ProverDriver protocol definition
- `src/config.py` — environment variable names and default constants
- `PROGRAM.md` — this file
- `docs/API_CONTRACT.md` — the API specification

## PR Gate

Every 5 successful ratchet steps (per loop), the agent opens a PR with:
1. Cumulative diff of all kept changes
2. Before/after eval scores
3. Notable experiment failures (for learning)

Human reviews and merges. No auto-merge.

## Preamble Gate

Any new `.lean` file added to `lean_workspace/LeanEcon/Preamble/` requires
human approval. No exceptions. Preamble entries are compiled Lean that
affects kernel-level correctness.

## Budget Constraints

- Formalizer experiments: ≤ $2 per experiment (LLM cost)
- Prover experiments: ≤ $5 per experiment (LLM cost)
- Monthly agent budget ceiling: $100 total across all loops
- Hard timeout: 300 seconds per verification attempt

## What Counts as an Experiment

An experiment is one atomic change to an editable-zone file, followed by a
full eval run. The change must be:
- Self-contained (no dependencies on other uncommitted changes)
- Reversible (git revert produces the prior state)
- Measurable (eval script produces a comparable score)

## Current Baselines (from v1, 2026-03-25)

- Formalizer-only tier-1: pass@1 = 1.000, semantic ≥4 rate = 0.833
- Formalizer-only tier-2: pass@1 = 0.667
- Theorem-stub verify: pass@1 = 1.000
- Raw-claim end-to-end: pass@1 = 0.333
- Latency p50: ~228s, p95: ~267s (end-to-end)

V2 targets: improve raw-claim end-to-end pass@1 to ≥0.667 within 2 weeks.
```

### Task 3: Write docs/API_CONTRACT.md

Full specification of the v2 API contract. Include for each endpoint:
- URL, method, purpose
- Request schema (Pydantic-style with field descriptions)
- Response schema
- Error codes
- Example curl command
- Behavioral guarantees (what it does and does NOT do)

Use the endpoint table from the contract section above. Key behavioral rules:
- `/search` never makes LLM calls
- `/formalize` includes scope check; returns `scope` field in response with values: `IN_SCOPE`, `NEEDS_DEFINITIONS`, `RAW_LEAN`
- `/formalize` returns `search_context` in response showing what retrieval data was used
- `/verify` accepts only a theorem string with sorry; returns 202 + job_id
- `/compile` accepts complete Lean code; returns compilation result synchronously
- SSE events use stages: `parse`, `formalize`, `prover_dispatch`, `agentic_init`, `agentic_setup`, `agentic_run`, `agentic_check`, `agentic_verify`

### Task 4: Write src/drivers/base.py

```python
"""Provider-agnostic interface for LLM-driven proving and formalization."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolDefinition:
    """A tool that the LLM can call during proving."""
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    """A tool call emitted by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Result of executing a tool call."""
    call_id: str
    content: str
    is_error: bool = False


@dataclass
class DriverEvent:
    """Progress event from the driver."""
    type: str  # "text", "tool_call", "tool_result", "done", "error"
    data: Any = None


@dataclass
class DriverConfig:
    """Configuration for a driver instance."""
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 1.0
    max_tokens: int = 4096
    timeout: float = 300.0
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ProverDriver(Protocol):
    """Provider-agnostic interface for LLM-driven agentic proving.

    Implementors handle the provider-specific API (Mistral, Gemini, HF, etc.)
    and expose a uniform async iteration interface. The proving harness manages
    tool execution, budget tracking, and file control; the driver just manages
    the LLM conversation loop.
    """

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g. 'mistral', 'gemini')."""
        ...

    async def prove(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[ToolDefinition],
        on_tool_call: Callable[[ToolCall], ToolResult],
        max_steps: int = 64,
    ) -> AsyncIterator[DriverEvent]:
        """Drive a proving loop.

        The driver sends the system/user prompts to the LLM, handles tool-use
        turns by calling on_tool_call for each tool invocation, and yields
        DriverEvents for progress tracking.

        The driver MUST:
        - Call on_tool_call for every tool call the LLM emits
        - Feed tool results back into the conversation
        - Yield DriverEvent(type="done") when the LLM signals completion
        - Yield DriverEvent(type="error") on unrecoverable failures
        - Respect max_steps as a hard ceiling on conversation turns

        The driver MUST NOT:
        - Execute tools itself (that's the harness's job via on_tool_call)
        - Manage proof files or checkpoints
        - Make decisions about proof strategy
        """
        ...


@runtime_checkable
class FormalizerDriver(Protocol):
    """Provider-agnostic interface for LLM-driven formalization.

    Simpler than ProverDriver — no tool-use loop, just a single
    structured generation call.
    """

    @property
    def name(self) -> str:
        ...

    async def formalize(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a Lean 4 theorem stub from the prompt.

        Returns the raw LLM output string. The formalizer module handles
        parsing, validation, and retry logic.
        """
        ...


# --- Driver Registry ---

_prover_drivers: dict[str, type] = {}
_formalizer_drivers: dict[str, type] = {}


def register_prover(name: str):
    """Decorator to register a ProverDriver implementation."""
    def decorator(cls):
        _prover_drivers[name] = cls
        return cls
    return decorator


def register_formalizer(name: str):
    """Decorator to register a FormalizerDriver implementation."""
    def decorator(cls):
        _formalizer_drivers[name] = cls
        return cls
    return decorator


def get_prover_driver(name: str, config: DriverConfig) -> ProverDriver:
    """Instantiate a registered ProverDriver by name."""
    if name not in _prover_drivers:
        available = ", ".join(_prover_drivers.keys()) or "(none)"
        raise ValueError(f"Unknown prover driver '{name}'. Available: {available}")
    return _prover_drivers[name](config)


def get_formalizer_driver(name: str, config: DriverConfig) -> FormalizerDriver:
    """Instantiate a registered FormalizerDriver by name."""
    if name not in _formalizer_drivers:
        available = ", ".join(_formalizer_drivers.keys()) or "(none)"
        raise ValueError(f"Unknown formalizer driver '{name}'. Available: {available}")
    return _formalizer_drivers[name](config)
```

### Task 5: Write src/config.py

Environment-driven configuration. Single source of truth for all constants.

```python
"""LeanEcon v2 configuration. Single source of truth for all runtime constants."""

from __future__ import annotations

import os
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEAN_WORKSPACE = PROJECT_ROOT / "lean_workspace"
LEAN_PROOF_DIR = LEAN_WORKSPACE / "LeanEcon"
PREAMBLE_DIR = LEAN_PROOF_DIR / "Preamble"
EVAL_CLAIMS_DIR = PROJECT_ROOT / "evals" / "claim_sets"
CACHE_DIR = PROJECT_ROOT / ".cache"
DB_PATH = PROJECT_ROOT / ".cache" / "jobs.db"

# --- LLM Provider ---
DEFAULT_DRIVER = os.getenv("LEANECON_DRIVER", "mistral")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "labs-leanstral-2603")
HF_TOKEN = os.getenv("HF_TOKEN", "")

# --- Lean ---
LEAN_RUN_CODE = os.getenv("LEAN_RUN_CODE", "lean_run_code")
LAKE_BUILD = os.getenv("LAKE_BUILD", "lake build")
LEAN_TIMEOUT = int(os.getenv("LEAN_TIMEOUT", "60"))

# --- Proving ---
MAX_PROVE_STEPS = int(os.getenv("MAX_PROVE_STEPS", "64"))
MAX_PROVE_TIMEOUT = int(os.getenv("MAX_PROVE_TIMEOUT", "300"))
MAX_SEARCH_TOOL_CALLS = int(os.getenv("MAX_SEARCH_TOOL_CALLS", "8"))
MAX_TOTAL_TOOL_CALLS = int(os.getenv("MAX_TOTAL_TOOL_CALLS", "40"))
PROVE_TEMPERATURE = float(os.getenv("PROVE_TEMPERATURE", "1.0"))

# --- API ---
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# --- Jobs ---
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "3600"))
JOB_MAX_CONCURRENT = int(os.getenv("JOB_MAX_CONCURRENT", "2"))

# --- Formalization ---
MAX_FORMALIZE_ATTEMPTS = int(os.getenv("MAX_FORMALIZE_ATTEMPTS", "3"))
FORMALIZE_TEMPERATURE = float(os.getenv("FORMALIZE_TEMPERATURE", "0.3"))

# --- Cache ---
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
```

### Task 6: Write src/models.py

Pydantic v2 request/response models for all endpoints. Key models:

- `SearchRequest(raw_claim: str, domain: str = "economics")`
- `SearchResponse(preamble_matches: list, curated_hints: list, domain: str, candidate_imports: list, candidate_identifiers: list)`
- `FormalizeRequest(raw_claim: str, preamble_names: list[str] | None = None)`
- `FormalizeResponse(success: bool, theorem_code: str | None, scope: str, search_context: dict, attempts: int, errors: list[str], ...)`
- `CompileRequest(lean_code: str)`
- `CompileResponse(success: bool, output: str, errors: list[str])`
- `VerifyRequest(theorem_with_sorry: str, max_steps: int = 64, timeout: int = 300)`
- `VerifyResponse` — returned via job polling, not directly
- `JobStatus(id: str, status: str, created_at: str, result: dict | None, ...)`
- `ExplainRequest(verification_result: dict)`
- `ExplainResponse(explanation: str)`
- `HealthResponse(status: str, lean_available: bool, driver: str, version: str)`
- `MetricsResponse(baselines: dict, uptime: float, ...)`

### Task 7: Write src/api.py (skeleton)

Thin FastAPI app. Each endpoint delegates to the appropriate module. No business logic in route handlers. For now, implement only `/health` and `/api/v2/search` fully. All other endpoints should return `501 Not Implemented` with a message like `"Coming in Phase 3"`.

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import API_HOST, API_PORT, CORS_ORIGINS

app = FastAPI(
    title="LeanEcon v2",
    description="Formal verification API for mathematical economics claims",
    version="2.0.0-alpha",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Task 8: Write skeleton test files

- `tests/conftest.py` — FastAPI test client fixture
- `tests/test_api_smoke.py` — health endpoint returns 200, search endpoint accepts a claim
- `tests/test_search.py` — placeholder
- `tests/test_formalizer.py` — placeholder
- `tests/test_prover.py` — placeholder
- `tests/test_store.py` — placeholder

### Task 9: Write pyproject.toml and requirements.txt

**requirements.txt:**
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0
httpx>=0.27.0
mistralai>=1.0.0
huggingface-hub>=0.25.0
aiosqlite>=0.20.0
python-dotenv>=1.0.0
```

**pyproject.toml:** Standard Python project config with ruff, pytest settings.

### Task 10: Write .env.example

```
MISTRAL_API_KEY=your_key_here
HF_TOKEN=your_hf_token_here
LEANECON_DRIVER=mistral
MISTRAL_MODEL=labs-leanstral-2603
PORT=8000
```

### Task 11: Write Dockerfile

Production Dockerfile for Railway deployment:
- Base: python:3.11-slim
- Install elan (Lean toolchain manager)
- Copy requirements and install
- Copy source
- Note: lean_workspace/ will be added after Phase 2B populates it
- CMD: uvicorn src.api:app --host 0.0.0.0 --port $PORT

### Task 12: Write .gitignore

Standard Python + Lean + IDE ignores:
```
__pycache__/
*.pyc
.env
.cache/
*.db
lean_workspace/build/
lean_workspace/.lake/
.vscode/
.idea/
dist/
*.egg-info/
```

### Task 13: Write README.md

Brief landing page:
- What LeanEcon v2 is (one paragraph)
- Quick start (clone, install, run)
- Link to docs/API_CONTRACT.md
- Link to docs/ARCHITECTURE.md
- Current status: "alpha — scaffold complete, core implementation in progress"
- License: Apache-2.0

### Task 14: Write CONTRIBUTING.md, NOTICE, TRADEMARK.md

Port the spirit from v1 but simplify:
- CONTRIBUTING: local validation commands, what makes a good change, doc rules
- NOTICE: Apache-2.0 attribution
- TRADEMARK: short brand guidance

---

## Validation Checklist

When done, verify:
1. `cd leanecon_v2 && python -c "from src.config import PROJECT_ROOT; print(PROJECT_ROOT)"` works
2. `pip install -r requirements.txt` succeeds
3. `python -m pytest tests/test_api_smoke.py -v` passes (health endpoint)
4. `ruff check src tests evals` passes
5. All directories exist with `__init__.py` where needed
6. `PROGRAM.md` exists with both autoresearch loops defined
7. `docs/API_CONTRACT.md` exists with all 9 endpoints specified
8. `src/drivers/base.py` defines `ProverDriver` and `FormalizerDriver` protocols
9. `.env.example` exists with all required variables

Commit everything with message: `feat: v2 scaffold — PROGRAM.md, API contract, provider-agnostic driver interface`

Push to `main` branch.
