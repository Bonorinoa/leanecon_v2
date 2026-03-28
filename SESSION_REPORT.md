# Session Report: Agentic Harness Eval Set & Timeout Fix

**Date:** 2026-03-28
**Scope:** Two tasks — (1) create `evals/claim_sets/agentic_harness.jsonl` and (2) fix the `/api/v2/verify` timeout path
**Snapshot:** 24/24 passed in 3m47s
---

## Task 1: Agentic Harness Eval Set

### Problem
Current eval sets (tier0/tier1/tier2) are mostly closable by single fast-path tactics (simp, aesop, field_simp, etc.). There was no evaluation set that forces the agentic proving loop to exercise its multi-step reasoning, definition unfolding, and tool coordination capabilities.

### Solution
Created `evals/claim_sets/agentic_harness.jsonl` with 13 theorem stubs:
- **10 provable** stubs that require 2-3 tactic steps
- **3 negative controls** (impossible theorems) that should fail quickly

### Key Design Insight
All LeanEcon preamble definitions (marshallian_demand, nkpc, profit, etc.) are `noncomputable`. Lean's single-step tactics (simp, ring, field_simp, rfl, etc.) cannot see through noncomputable function applications without explicit `unfold`. This means any theorem involving a preamble definition in the goal **requires at least `unfold` before algebraic tactics can operate**, systematically defeating the fast path.

### Provable Stubs

| ID | Preamble(s) | Expected Proof | Steps |
|----|------------|----------------|-------|
| `ag_walras_law` | MarshallianDemand | unfold both defs -> field_simp -> ring | 3 |
| `ag_nkpc_zero_gap` | PhillipsCurve | unfold nkpc -> ring | 2 |
| `ag_expected_payoff_pure_row` | ExpectedPayoff | unfold -> ring | 2 |
| `ag_rra_from_ara` | ArrowPrattARA + RRA | unfold both -> ring | 2 |
| `ag_profit_zero_breakeven` | ProfitFunction | unfold profit -> linarith | 2 |
| `ag_budget_set_cheaper_bundle` | BudgetSet | unfold at h and goal -> linarith | 2 |
| `ag_bellman_linear_utility` | BellmanEquation | unfold -> simp | 2 |
| `ag_present_value_one_period` | DiscountFactor | unfold -> have (1-beta != 0) -> field_simp | 3 |
| `ag_solow_steady_state_condition` | SolowSteadyState | unfold both -> exact hss | 2 |
| `ag_income_elasticity_unit` | IncomeElasticity | unfold -> rw [hlinear] -> field_simp | 3 |

### Negative Controls

| ID | Why Impossible |
|----|---------------|
| `ag_neg_false_arithmetic` | `1 + 1 = 3` is provably false |
| `ag_neg_wrong_demand` | Claims demand = m/p1 (missing alpha), contradicted by alpha != 1 hypothesis |
| `ag_neg_division_by_zero` | PV with beta=1 gives 0/0=0 in Lean, not x*T |

### Verification Results
- All 13 stubs compile with `sorry` (exit code 0, only "declaration uses sorry" warning)
- All 10 provable stubs' intended multi-step proofs compile successfully
- **10/10 provable stubs resist ALL fast-path tactics** (simpa, aesop, simp, rfl, norm_num, exact?, trivial, ring, field_simp, decide)
- The conditional tactic `simpa [in_budget_set] using hbudget` was also verified to fail on `ag_budget_set_cheaper_bundle` (type mismatch: hbudget is about (x1,x2) while goal is about (y1,y2))

### Prover Prompt Enhancement
Added "think lemma-by-lemma" reasoning guidance to `src/prover/prompts.py`:
- Encourages the LLM to analyze definitions before attempting tactics
- Lists common multi-step patterns: `unfold -> field_simp -> ring`, `unfold at h -> linarith`, etc.
- Teaches the critical "unfold first" heuristic for noncomputable preamble definitions
- Should reduce wasted tool calls from trial-and-error

---

## Task 2: Timeout Path Fix

### Problem
When a verification job hit its timeout, three things were broken:
1. **No structured result data:** `job_store.fail()` was called without a `result` dict, so the job's result was `null`
2. **Harness state was inaccessible:** The `VerificationHarness` was created inside the `try` block, so after timeout we couldn't access its budget tracker or tool history
3. **SSE terminal event lacked result data:** The `fail()` method's published event only included `type`, `status`, `error` — no structured result

### Changes Made

#### `src/api.py` — `_run_verify_job()`
- Moved `harness = _verification_harness()` **outside** the `asyncio.timeout()` block so it survives timeout
- Added `_progress_tracker()` closure that tracks the `last_stage` variable
- Added `_partial_result()` helper that builds structured failure data from the harness's current state:
  ```python
  {"partial": True, "stop_reason": "timeout"|"exception",
   "tool_calls_made": N, "last_stage": "...",
   "tool_history": [...], "tool_budget": {...}}
  ```
- Both `TimeoutError` and general `Exception` handlers now pass this structured result to `job_store.fail()`

#### `src/store/jobs.py` — `JobStore.fail()`
- The SSE terminal event now includes `"result"` when a result dict is provided
- Before: `{"type": "complete", "status": "failed", "job_id": ..., "error": ...}`
- After: same, plus `"result": {...}` when result is not None

### Test Coverage
- `test_timeout_returns_structured_partial_result` (test_prover.py): Uses a fake slow driver to trigger timeout, verifies harness state is accessible and partial result structure is correct
- `test_job_store_fail_with_structured_result` (test_store.py): Verifies the store persists structured result on fail AND publishes it to SSE subscribers

### Behavior After Fix

When submitting an impossible theorem like `theorem impossible : (0 : ℝ) = 1 := by sorry`:
1. Job status transitions: `queued` -> `running` -> `failed` (not stuck in `running`)
2. Result includes: `{"partial": true, "stop_reason": "timeout", "tool_calls_made": N, "last_stage": "fast_path"|"provider", "tool_history": [...], "tool_budget": {...}}`
3. SSE stream emits terminal event: `{"type": "complete", "status": "failed", "error": "Verification timed out after 300s.", "result": {...}}`

---

## Files Changed

| File | Change |
|------|--------|
| `evals/claim_sets/agentic_harness.jsonl` | **NEW** — 13 agentic eval stubs |
| `src/prover/prompts.py` | Added "think lemma-by-lemma" reasoning strategy to `PROVER_SYSTEM_PROMPT` |
| `src/api.py` | Fixed timeout path in `_run_verify_job()` to return structured failure data |
| `src/store/jobs.py` | Fixed `fail()` SSE event to include result data |
| `tests/test_prover.py` | Added timeout test + SlowDriver fake |
| `tests/test_store.py` | Added structured failure result test |

---

## Proposed Next Steps

1. **Run the agentic harness eval end-to-end** with the production Mistral driver: `python -m evals.prover_only --claim-set agentic_harness`. This will establish the agentic baseline: what fraction of the 10 provable stubs does the current system prove? Target: >= 7/10 (0.70 pass@1).

2. **Tune the "unfold first" heuristic in the fast path**: Consider adding `unfold <detected_def>` as a fast-path prefix. If the fast path detects a known preamble name in the theorem (e.g., `marshallian_demand_good1`), it could try `unfold marshallian_demand_good1; ring` as a composite fast-path tactic. This would move some currently-agentic stubs into the fast path, improving latency.

3. **Add fast-path composition**: Extend `suggest_fast_path_tactics()` to generate 2-tactic compositions (e.g., `unfold X; ring`, `unfold X; linarith`, `unfold X at h ⊢; linarith`). This is a middle ground between single-tactic fast path and full agentic loop.

4. **Expand the agentic harness**: The current 10 provable stubs focus on `unfold`-based multi-step proofs. Future additions should include:
   - Theorems requiring `have` intermediate lemmas (like `ag_present_value_one_period`)
   - Theorems requiring `induction` or `cases`
   - Theorems combining multiple preamble modules (welfare + consumer theory)
   - Harder algebraic manipulations (CES production function properties)

5. **Improve negative control detection**: The agentic loop currently has no mechanism to recognize an impossible theorem and fail early. Consider adding a "give up" tool or confidence threshold where the agent can signal "this theorem appears unprovable" after N failed attempts.

6. **Fix `asyncio.timeout` interaction with blocking subprocesses**: The current `asyncio.timeout` cannot interrupt synchronous `subprocess.run` calls in `compile_check`. Consider using `asyncio.create_subprocess_exec` for Lean compilation to make it truly cancellable. This would allow timeout to fire *during* a compilation rather than only at the next `await` point.

7. **Monitor the agentic budget efficiency**: The current budget is 40 total tool calls / 8 search calls. With the "think lemma-by-lemma" prompt, the agentic loop should need fewer calls (target: 5-10 calls for a 2-3 step proof). Track `tool_calls_made` across the harness eval to calibrate the budget.
