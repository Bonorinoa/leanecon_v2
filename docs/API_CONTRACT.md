# LeanEcon v2 API Contract

This document is the canonical API specification for LeanEcon v2. The contract
is explicit by design: retrieval, formalization, compilation, proving,
explanation, jobs, and metrics are separate concerns.

## Global Rules

- `/verify` proves only the supplied theorem string. It does not classify,
  formalize, or retrieve context.
- `/search` is deterministic and never makes LLM calls.
- `/formalize` performs scope checking, calls search internally, and returns the
  retrieval context it used.
- Retrieval context is advisory. It never silently influences `/verify`.
- `/compile` accepts complete Lean code and runs a synchronous local compile
  check.
- `/verify` accepts a theorem with `sorry` and returns `202 Accepted` with a
  `job_id`.
- SSE progress events use the stages `parse`, `formalize`, `prover_dispatch`,
  `agentic_init`, `agentic_setup`, `agentic_run`, `agentic_check`,
  `agentic_verify`.

## Common Error Shape

```python
class ErrorResponse(BaseModel):
    detail: str = Field(description="Human-readable error message.")
```

## `GET /health`

**Purpose:** Liveness probe and alpha environment status.

### Request Schema

No request body.

### Response Schema

```python
class HealthResponse(BaseModel):
    status: str = Field(description="Overall API status.")
    lean_available: bool = Field(description="Whether Lean is available.")
    driver: str = Field(description="Configured default driver name.")
    version: str = Field(description="API version string.")
```

### Error Codes

- `500` unexpected server failure

### Example

```bash
curl http://localhost:8000/health
```

### Behavioral Guarantees

- Returns liveness data synchronously.
- Does not call any LLM provider.
- Does not run proving or formalization work.
- In Phase 2A, `lean_available` may be `false` even when the API is healthy.

## `POST /api/v2/search`

**Purpose:** Deterministic retrieval for preamble matching, curated hints,
concept lookup stubs, and domain tagging.

### Request Schema

```python
class SearchRequest(BaseModel):
    raw_claim: str = Field(description="Natural-language claim to search for.")
    domain: str = Field(default="economics", description="Requested domain tag.")
```

### Response Schema

```python
class PreambleMatch(BaseModel):
    name: str = Field(description="Matched preamble or Lean artifact name.")
    path: str | None = Field(default=None, description="Relative file path.")
    score: float = Field(description="Deterministic lexical score.")
    reason: str = Field(description="Why the match was returned.")


class CuratedHint(BaseModel):
    name: str = Field(description="Hint bundle name.")
    description: str = Field(description="Why this hint may help.")
    keywords: list[str] = Field(description="Keywords that triggered the hint.")
    candidate_imports: list[str] = Field(description="Suggested Lean imports.")
    candidate_identifiers: list[str] = Field(
        description="Suggested Lean identifiers to inspect."
    )


class SearchResponse(BaseModel):
    preamble_matches: list[PreambleMatch]
    curated_hints: list[CuratedHint]
    domain: str
    candidate_imports: list[str]
    candidate_identifiers: list[str]
```

### Error Codes

- `400` invalid request payload
- `422` schema validation error
- `500` unexpected server failure

### Example

```bash
curl -X POST http://localhost:8000/api/v2/search \
  -H "Content-Type: application/json" \
  -d '{"raw_claim":"Every competitive equilibrium is Pareto efficient."}'
```

### Behavioral Guarantees

- Never makes LLM calls.
- Returns deterministic results for the same request and local filesystem state.
- May return empty `preamble_matches` when the Lean workspace has not yet been
  populated.
- Returns advisory imports and identifiers only; no hidden proving occurs.

## `POST /api/v2/formalize`

**Purpose:** Produce a Lean theorem stub with `sorry`, including scope checks and
the retrieval context used to shape the statement.

### Request Schema

```python
class FormalizeRequest(BaseModel):
    raw_claim: str = Field(description="Claim to formalize.")
    preamble_names: list[str] | None = Field(
        default=None,
        description="Optional preferred preamble entries from the caller.",
    )
```

### Response Schema

```python
class FormalizeResponse(BaseModel):
    success: bool
    theorem_code: str | None
    scope: Literal["IN_SCOPE", "NEEDS_DEFINITIONS", "RAW_LEAN"]
    search_context: dict[str, Any]
    attempts: int
    errors: list[str]
    message: str | None = None
```

### Error Codes

- `400` invalid or empty claim
- `422` schema validation error
- `500` formalizer failure

### Example

```bash
curl -X POST http://localhost:8000/api/v2/formalize \
  -H "Content-Type: application/json" \
  -d '{"raw_claim":"A Walrasian equilibrium exists under standard assumptions."}'
```

### Behavioral Guarantees

- Calls search logic internally before statement generation.
- Returns a `scope` value from `IN_SCOPE`, `NEEDS_DEFINITIONS`, or `RAW_LEAN`.
- Returns `search_context` showing the deterministic retrieval used.
- Produces a theorem stub with `sorry`; it does not prove the theorem.

## `POST /api/v2/compile`

**Purpose:** Synchronous local Lean compile check for complete Lean code.

### Request Schema

```python
class CompileRequest(BaseModel):
    lean_code: str = Field(description="Complete Lean source to compile.")
```

### Response Schema

```python
class CompileResponse(BaseModel):
    success: bool
    output: str = Field(description="Compiler stdout and summary.")
    errors: list[str] = Field(description="Compiler diagnostics.")
```

### Error Codes

- `400` missing or incomplete Lean source
- `422` schema validation error
- `500` compiler wrapper failure

### Example

```bash
curl -X POST http://localhost:8000/api/v2/compile \
  -H "Content-Type: application/json" \
  -d '{"lean_code":"theorem demo : True := by trivial"}'
```

### Behavioral Guarantees

- Runs synchronously.
- Accepts complete Lean code, not partial claims.
- Does not classify, retrieve, or formalize.
- Does not enqueue a job.

## `POST /api/v2/verify`

**Purpose:** Queue provider-backed proof generation and kernel verification for a
caller-supplied theorem stub.

### Request Schema

```python
class VerifyRequest(BaseModel):
    theorem_with_sorry: str = Field(
        description="Lean theorem stub containing `sorry`."
    )
    max_steps: int = Field(default=64, description="Hard ceiling on agentic steps.")
    timeout: int = Field(default=300, description="Verification timeout in seconds.")
```

### Response Schema

```python
class VerifyAcceptedResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    message: str
```

### Error Codes

- `400` theorem is missing or does not contain `sorry`
- `422` schema validation error
- `429` concurrency limit reached
- `500` job enqueue failure

### Example

```bash
curl -X POST http://localhost:8000/api/v2/verify \
  -H "Content-Type: application/json" \
  -d '{"theorem_with_sorry":"theorem demo : True := by sorry"}'
```

### Behavioral Guarantees

- Returns `202 Accepted` with a `job_id`.
- Does not run formalization or retrieval implicitly.
- Treats the supplied theorem text as the only proving target.
- Proof generation and kernel checks happen asynchronously via the job system.

## `GET /api/v2/jobs/{id}`

**Purpose:** Poll the current status and final result of a verification job.

### Request Schema

Path parameter: `id: str`

### Response Schema

```python
class JobStatus(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None
```

### Error Codes

- `404` job not found
- `500` job store failure

### Example

```bash
curl http://localhost:8000/api/v2/jobs/job_123
```

### Behavioral Guarantees

- Returns polling-friendly JSON.
- Does not mutate job state except for read-side timestamps or access metadata.
- Final proof artifacts and diagnostics are returned through `result`.

## `GET /api/v2/jobs/{id}/stream`

**Purpose:** Stream SSE progress events for a verification job.

### Request Schema

Path parameter: `id: str`

### Response Schema

Server-Sent Events with a JSON payload similar to:

```json
{
  "job_id": "job_123",
  "stage": "agentic_run",
  "message": "Driver requested another tool call.",
  "timestamp": "2026-03-26T21:00:00Z"
}
```

### Error Codes

- `404` job not found
- `500` stream initialization failure

### Example

```bash
curl -N http://localhost:8000/api/v2/jobs/job_123/stream
```

### Behavioral Guarantees

- Uses SSE, not WebSockets.
- Emits stage names only from the approved stage list.
- Streaming is observational; it does not change proof strategy.

## `POST /api/v2/explain`

**Purpose:** Generate a natural-language explanation of a verification result.

### Request Schema

```python
class ExplainRequest(BaseModel):
    verification_result: dict[str, Any] = Field(
        description="Structured verification result returned by the jobs API."
    )
```

### Response Schema

```python
class ExplainResponse(BaseModel):
    explanation: str = Field(description="Plain-language explanation.")
```

### Error Codes

- `400` malformed verification result
- `422` schema validation error
- `500` explanation generation failure

### Example

```bash
curl -X POST http://localhost:8000/api/v2/explain \
  -H "Content-Type: application/json" \
  -d '{"verification_result":{"status":"verified","theorem":"demo"}}'
```

### Behavioral Guarantees

- Produces explanation only.
- Does not re-run proving or compilation.
- Treats the verification result as the source of truth.

## `GET /api/v2/metrics`

**Purpose:** Return benchmark snapshots and system telemetry.

### Request Schema

No request body.

### Response Schema

```python
class MetricsResponse(BaseModel):
    baselines: dict[str, Any]
    uptime: float
    queue_depth: int = 0
    active_jobs: int = 0
```

### Error Codes

- `500` metrics collection failure

### Example

```bash
curl http://localhost:8000/api/v2/metrics
```

### Behavioral Guarantees

- Read-only endpoint.
- Returns operational and benchmarking metadata only.
- Does not trigger evals or mutate job state.
