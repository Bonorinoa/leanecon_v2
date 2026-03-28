# LeanEcon v2 — Phase 3 Codex Briefing: Core Implementation

**Date:** March 26, 2026
**Prerequisite:** Phase 2A scaffold is complete. Lean workspace builds. `/health` and `/api/v2/search` work.
**Goal:** Wire up the remaining 7 endpoints so the API is functionally complete.

---

## Context

The v2 repo has two layers right now:

1. **v2 scaffold** (Phase 2A) — clean structure under `src/`, with `ProverDriver` protocol, models, config, search engine, and stub endpoints returning 501.
2. **v1 source files** carried over during Lean workspace setup — these sit at `src/formalizer.py`, `src/formalization_search.py`, `src/preamble_library.py`, `src/prover_backend.py`, and `tests/test_formalizer.py`. They use v1 import paths (`from prompts import ...`, `from lean_verifier import ...`) and will NOT run as-is.

**Your job:** Port the *logic* from v1 files into the v2 scaffold modules, then remove or archive the v1 top-level files. Do NOT try to make v1 files run in-place — adapt their logic into the v2 module structure.

---

## Architecture Reminder

```
Request → src/api.py (thin router)
            ↓
        src/search/engine.py      ← deterministic, no LLM (already working)
        src/formalizer/formalizer.py ← LLM call via FormalizerDriver
        src/prover/harness.py     ← orchestrates ProverDriver + file_controller + tool_tracker
            ↓
        src/drivers/mistral.py    ← Mistral Conversations API
            ↓
        src/lean/compiler.py      ← lean_run_code, lake env lean
            ↓
        src/store/jobs.py         ← SQLite job persistence
```

Key rule: **No business logic in `src/api.py`.** Route handlers call module functions and return their results.

---

## Task List (execute in order)

### Task 1: Implement `src/lean/compiler.py` (20 min)

This is the foundation — everything else depends on being able to compile Lean code.

Port from v1's `lean_verifier.py` (referenced in `src/formalizer.py`). Implement:

```python
"""Lean 4 compilation primitives for LeanEcon v2."""

import subprocess
import tempfile
from pathlib import Path
from src.config import LEAN_WORKSPACE, LEAN_TIMEOUT

def lean_run_code(lean_code: str, *, timeout: int = LEAN_TIMEOUT) -> dict:
    """Compile a standalone Lean snippet using `lake env lean`.

    Writes lean_code to a temp file inside lean_workspace/, runs
    `lake env lean <file>`, and returns:
      {"success": bool, "stdout": str, "stderr": str, "exit_code": int}

    This is the sorry-validation path: Lean compiles `sorry` with exit 0
    but emits a warning. The caller decides whether sorry is acceptable.
    """
    ...

def sorry_in_output(stderr: str) -> bool:
    """Check if Lean output contains sorry warnings."""
    return "declaration uses 'sorry'" in stderr or "'sorry'" in stderr

def has_axiom_warnings(stderr: str) -> list[str]:
    """Extract non-standard axiom usage from Lean output."""
    standard = {"propext", "Classical.choice", "Quot.sound"}
    # parse "uses axioms: [...]" lines, return non-standard ones
    ...

def compile_check(lean_code: str, *, timeout: int = LEAN_TIMEOUT) -> dict:
    """Full compilation check. Returns structured result for /api/v2/compile."""
    result = lean_run_code(lean_code, timeout=timeout)
    return {
        "success": result["success"] and not sorry_in_output(result["stderr"]),
        "has_sorry": sorry_in_output(result["stderr"]),
        "axiom_warnings": has_axiom_warnings(result["stderr"]),
        "output": result["stdout"],
        "errors": [result["stderr"]] if not result["success"] else [],
        "exit_code": result["exit_code"],
    }
```

**Implementation detail:** The temp file MUST be created inside `lean_workspace/` so that `lake env lean` can resolve Mathlib and preamble imports. Use a unique filename like `_v2_check_{uuid}.lean` and clean up after.

### Task 2: Implement `src/lean/validators.py` (10 min)

```python
"""Sorry detection and axiom validation."""

def detect_sorry(lean_code: str) -> bool:
    """Check if source code contains sorry."""
    return "sorry" in lean_code

def validate_axioms(stderr: str) -> dict:
    """Parse Lean compiler output for axiom usage."""
    # Return {"standard_only": bool, "axioms_used": [...], "non_standard": [...]}
    ...
```

### Task 3: Implement `src/store/jobs.py` — SQLite-backed job store (20 min)

Replace v1's in-memory dict with SQLite. Same interface, survives restarts.

```python
"""SQLite-backed job store for async verification jobs."""

import sqlite3
import json
import uuid
import threading
from datetime import datetime, timezone
from src.config import DB_PATH, JOB_TTL_SECONDS

class JobStore:
    def __init__(self, db_path=DB_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
        # Keep in-memory subscriber queues for SSE (same as v1)
        self._subscribers: dict[str, list] = {}

    def _init_db(self):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result TEXT,
                    error TEXT
                )
            """)

    def create(self, job_id: str | None = None) -> str: ...
    def start(self, job_id: str) -> None: ...
    def complete(self, job_id: str, result: dict) -> None: ...
    def fail(self, job_id: str, error: str) -> None: ...
    def get(self, job_id: str) -> dict | None: ...
    def publish(self, job_id: str, event: dict) -> None: ...
    def subscribe(self, job_id: str) -> queue.Queue: ...
    def unsubscribe(self, job_id: str, q: queue.Queue) -> None: ...

job_store = JobStore()
```

SSE subscribers remain in-memory (they're per-connection ephemeral state). Only job metadata and results go to SQLite.

### Task 4: Implement `src/formalizer/prompts.py` (15 min)

Port the prompt templates from v1's `src/prompts.py`. This file is in the **autoresearchable zone** — agents can modify it later.

Key prompts to port:
- `build_formalize_prompt(claim, context: FormalizationContext)` → system prompt for theorem stub generation
- `build_repair_prompt(claim, lean_code, errors, bucket)` → repair prompt after compilation failure
- `DIAGNOSE_SYSTEM_PROMPT` → for failure diagnosis

Adapt for v2:
- Remove the classify prompt (scope check is now deterministic in `formalizer.py`)
- The formalize prompt should reference the search context (preamble block, candidate imports, shape guidance) as advisory information
- Keep the prompt structure but make it work with the `FormalizerDriver` interface (system_prompt + user_prompt, not messages list)

### Task 5: Implement `src/formalizer/formalizer.py` — full version (25 min)

Port the core formalization logic from v1's `src/formalizer.py`. The v2 version should:

1. Call `search_claim()` from `src/search/engine.py` to get retrieval context
2. Build the formalize prompt using `src/formalizer/prompts.py`
3. Call the `FormalizerDriver` to generate a theorem stub
4. Run `lean_run_code()` to validate the stub compiles with sorry
5. If compilation fails, classify the error bucket and attempt repair (up to `MAX_FORMALIZE_ATTEMPTS`)
6. Return a `FormalizeResponse` with the theorem code, scope, search context, and diagnostics

```python
async def formalize_claim(
    raw_claim: str,
    preamble_names: list[str] | None = None,
    driver: FormalizerDriver | None = None,
) -> FormalizeResponse:
    """Full formalization pipeline: search → prompt → generate → validate → repair."""

    # 1. Scope check (deterministic)
    scope = scope_check(raw_claim)
    if scope == "RAW_LEAN":
        return FormalizeResponse(success=True, theorem_code=raw_claim, scope=scope, ...)

    # 2. Search context
    search_result = search_claim(raw_claim)

    # 3. Build prompt
    system_prompt, user_prompt = build_formalize_prompt(raw_claim, search_result, preamble_names)

    # 4. Generate via driver
    driver = driver or _get_default_formalizer_driver()
    raw_output = await driver.formalize(system_prompt=system_prompt, user_prompt=user_prompt)

    # 5. Parse and validate
    theorem_code = strip_fences(raw_output)
    validation = lean_run_code(theorem_code)

    # 6. Repair loop if needed
    ...

    return FormalizeResponse(...)
```

**Important:** Port the repair bucket classification from v1 (`classify_repair_bucket`). The five buckets are: `UNKNOWN_IMPORT_MODULE`, `UNKNOWN_IDENTIFIER`, `TYPECLASS_INSTANCE`, `SYNTAX_NOTATION`, `SEMANTIC_MISMATCH`.

### Task 6: Implement `src/drivers/mistral.py` — real driver (25 min)

Replace the stub with the actual Mistral Conversations API integration. Port from v1's `src/agentic_prover.py` and `src/leanstral_utils.py`.

```python
"""Mistral Conversations API driver for LeanEcon v2."""

from __future__ import annotations
from mistralai import Mistral
from src.drivers.base import (
    ProverDriver, FormalizerDriver, DriverConfig, DriverEvent,
    ToolDefinition, ToolCall, ToolResult,
    register_prover, register_formalizer,
)

@register_formalizer("mistral")
class MistralFormalizerDriver:
    """Single-turn formalization via Mistral chat completions."""

    def __init__(self, config: DriverConfig):
        self._client = Mistral(api_key=config.api_key)
        self._model = config.model
        self._config = config

    @property
    def name(self) -> str:
        return "mistral"

    async def formalize(self, *, system_prompt, user_prompt, max_tokens=4096) -> str:
        response = await self._client.chat.complete_async(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._config.temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


@register_prover("mistral")
class MistralProverDriver:
    """Agentic proving via Mistral Conversations API with tool use."""

    def __init__(self, config: DriverConfig):
        self._client = Mistral(api_key=config.api_key)
        self._model = config.model
        self._config = config

    @property
    def name(self) -> str:
        return "mistral"

    async def prove(self, *, system_prompt, user_prompt, tools, on_tool_call, max_steps=64):
        # Port the run_async loop from v1's agentic_prover.py:
        # 1. Start a conversation with system + user prompt
        # 2. On each turn, check if model emits tool_calls
        # 3. For each tool_call, invoke on_tool_call() and feed result back
        # 4. Continue until model signals done, error, or max_steps reached
        # 5. Yield DriverEvent for each step
        #
        # The v1 code uses client.agents.run_async() which manages the
        # conversation loop internally. For v2, use chat.complete_async()
        # with explicit tool-call handling for more control.
        ...
```

**Key porting decision:** V1 uses `client.agents.run_async()` which is Mistral's managed agent loop. For v2, prefer `client.chat.complete_async()` with explicit tool handling. This gives us more control over budget enforcement, logging, and the ability to swap providers. The `on_tool_call` callback pattern makes this clean — the driver calls it, gets back a `ToolResult`, and feeds it into the next turn.

### Task 7: Implement `src/prover/harness.py` — real harness (20 min)

Port the orchestration logic from v1's `agentic_prover.py`. The harness:

1. Receives a theorem with sorry
2. Initializes `ProofFileController` (write theorem to temp file)
3. Defines the tool set (apply_tactic, lean_diagnostic_messages, lean_goal, search tools)
4. Creates `on_tool_call` callback that dispatches to the right handler
5. Calls `driver.prove()` and tracks progress via `BudgetTracker`
6. After the driver finishes, runs final verification via `lean_run_code`
7. Returns structured result

```python
async def run_verification(
    theorem_with_sorry: str,
    job_id: str,
    driver: ProverDriver,
    on_progress: Callable | None = None,
) -> dict:
    """Full verification pipeline: init → prove → verify → result."""
    controller = ProofFileController()
    tracker = BudgetTracker()

    # Initialize working file
    controller.initialize(theorem_with_sorry)

    # Try local tactic fast path first
    fast_result = try_fast_path(theorem_with_sorry, controller)
    if fast_result:
        return fast_result

    # Define tools
    tools = build_tool_definitions(controller)

    # Build on_tool_call dispatcher
    def handle_tool_call(call: ToolCall) -> ToolResult:
        return dispatch_tool(call, controller, tracker)

    # Run the agentic loop
    async for event in driver.prove(
        system_prompt=build_prover_instructions(controller),
        user_prompt=build_prover_prompt(theorem_with_sorry, controller),
        tools=tools,
        on_tool_call=handle_tool_call,
        max_steps=MAX_PROVE_STEPS,
    ):
        if on_progress:
            on_progress(event)

    # Final verification
    final_code = controller.current_lean_code
    result = lean_run_code(final_code)

    controller.cleanup()
    return build_verification_result(result, tracker)
```

### Task 8: Wire up remaining API endpoints in `src/api.py` (15 min)

Replace the 501 stubs with real implementations:

```python
@app.post("/api/v2/formalize", response_model=FormalizeResponse)
async def formalize(request: FormalizeRequest) -> FormalizeResponse:
    return await formalize_claim(request.raw_claim, request.preamble_names)

@app.post("/api/v2/compile", response_model=CompileResponse)
async def compile_endpoint(request: CompileRequest) -> CompileResponse:
    result = compile_check(request.lean_code)
    return CompileResponse(**result)

@app.post("/api/v2/verify", status_code=202)
async def verify(request: VerifyRequest) -> dict:
    job_id = job_store.create()
    # Launch verification in background thread
    background_tasks.add_task(
        _run_verification_job, job_id, request.theorem_with_sorry,
        request.max_steps, request.timeout
    )
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/v2/jobs/{job_id}")
async def get_job(job_id: str) -> JobStatus:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobStatus(**job)

@app.get("/api/v2/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    # SSE streaming — port from v1's StreamingResponse pattern
    ...

@app.post("/api/v2/explain")
async def explain(request: ExplainRequest) -> ExplainResponse:
    # Single LLM call to explain verification result in natural language
    ...

@app.get("/api/v2/metrics")
async def metrics() -> MetricsResponse:
    return MetricsResponse(
        baselines=CURRENT_BASELINES,
        uptime=monotonic() - START_TIME,
        driver=DEFAULT_DRIVER,
        version=APP_VERSION,
    )
```

### Task 9: Implement eval harnesses (15 min)

**`evals/formalizer_only.py`:**
```python
"""Formalizer ratchet scoring function.

Usage: python evals/formalizer_only.py [--claims evals/claim_sets/tier1_core.jsonl]
Outputs: pass@1, semantic scores, latency stats
"""
# Read claims from JSONL
# For each: POST /api/v2/formalize → check success
# Compute pass@1 = successes / total
# Print single-line summary + write full report
```

**`evals/prover_only.py`:**
```python
"""Prover ratchet scoring function.

Usage: python evals/prover_only.py [--stubs evals/claim_sets/theorem_stubs.jsonl]
Outputs: pass@1, latency p50/p95, tool call stats
"""
# Read pre-formalized theorem stubs
# For each: POST /api/v2/verify → poll until complete
# Compute pass@1
# Print single-line summary + write full report
```

Create `evals/claim_sets/tier1_core.jsonl` with at least these claims:
```jsonl
{"claim": "1 + 1 = 2", "tier": 1, "category": "ALGEBRAIC"}
{"claim": "Under CRRA utility, relative risk aversion equals gamma", "tier": 1, "category": "DEFINABLE", "preambles": ["crra_utility"]}
{"claim": "Cobb-Douglas output elasticity w.r.t. capital equals alpha", "tier": 1, "category": "DEFINABLE", "preambles": ["cobb_douglas_2factor"]}
{"claim": "The budget constraint p1*x1 + p2*x2 = m is satisfied when all income is spent", "tier": 1, "category": "ALGEBRAIC"}
```

### Task 10: Clean up v1 files (5 min)

Move these v1 top-level files to `src/_v1_archive/` (do NOT delete — they're reference material):
- `src/formalizer.py` → `src/_v1_archive/formalizer.py`
- `src/formalization_search.py` → `src/_v1_archive/formalization_search.py`
- `src/prover_backend.py` → `src/_v1_archive/prover_backend.py`

Keep `src/preamble_library.py` — it's already being used by the v2 search engine.

Update `tests/test_formalizer.py` to import from v2 paths:
- `from src.formalizer.formalizer import formalize_claim, scope_check`
- Remove imports that reference v1 modules (`from formalizer import ...`)
- Keep test logic but adapt to v2 response shapes

### Task 11: Validate (10 min)

Run in order:
```bash
ruff check src tests evals
python -m pytest tests/test_api_smoke.py -v
python -m pytest tests/ -v --ignore=tests/test_formalizer.py  # skip until v2 tests adapted
```

Verify these endpoints return non-501 responses:
```bash
# Health
curl http://localhost:8000/health

# Search
curl -X POST http://localhost:8000/api/v2/search \
  -H "Content-Type: application/json" \
  -d '{"raw_claim": "CRRA utility risk aversion"}'

# Compile (needs Lean)
curl -X POST http://localhost:8000/api/v2/compile \
  -H "Content-Type: application/json" \
  -d '{"lean_code": "import Mathlib\n#check Nat.add_comm"}'

# Metrics
curl http://localhost:8000/api/v2/metrics
```

Commit with: `feat: phase 3 — core implementation (formalizer, prover harness, Mistral driver, SQLite jobs, eval harnesses)`

---

## Reference: What to port from which v1 file

| v1 file | What to port | v2 destination |
|---------|-------------|----------------|
| `src/formalizer.py` → `formalize()` | Formalization loop, repair buckets, sorry validation | `src/formalizer/formalizer.py` |
| `src/formalizer.py` → `classify_claim()` | Preamble rescue logic only (scope check is now deterministic) | `src/formalizer/formalizer.py` |
| `src/prompts.py` | `build_formalize_prompt`, `build_repair_prompt`, `DIAGNOSE_SYSTEM_PROMPT` | `src/formalizer/prompts.py` |
| `src/agentic_prover.py` | Tool definitions, `_make_apply_tactic`, `_build_instructions`, run loop | `src/prover/harness.py` + `src/drivers/mistral.py` |
| `src/lean_verifier.py` | `run_direct_lean_check`, `write_lean_file` | `src/lean/compiler.py` |
| `src/leanstral_utils.py` | `call_leanstral`, `strip_fences`, `get_client` | `src/drivers/mistral.py` (internalized) |
| `src/formalization_search.py` | `FormalizationContext`, `build_formalization_context` | Already covered by `src/search/engine.py` |
| `src/preamble_library.py` | Keep as-is — already used by search engine | `src/preamble_library.py` (no move) |
| `src/job_store.py` | `JobStore` interface, SSE subscriber pattern | `src/store/jobs.py` (SQLite version) |
| `src/result_cache.py` | `FormalizationCache` | `src/store/cache.py` |
| `src/proof_file_controller.py` | `ProofFileController` | `src/prover/file_controller.py` (already scaffolded) |

## Important constraints

- **Do NOT modify** `src/api.py` endpoint signatures, `src/models.py` schemas, `src/drivers/base.py` protocol, or `src/config.py` variable names. These are off-limits per PROGRAM.md.
- **Do NOT add new dependencies** beyond what's in `requirements.txt` without noting it.
- **The Mistral driver must use `mistralai` SDK.** The model string is `labs-leanstral-2603`.
- **All Lean temp files** must be created inside `lean_workspace/` and cleaned up after use.
- **SSE uses `text/event-stream`** content type via FastAPI `StreamingResponse`.
