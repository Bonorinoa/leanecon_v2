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
- V2 (2026-03-28) formalizer-only tier0_smoke: pass@1 = 1.000, latency p50 = 0.006s, p95 = 0.008s
- V2 (2026-03-28) formalizer-only tier1_core: pass@1 = 1.000, latency p50 = 0.006s, p95 = 0.007s
- V2 (2026-03-28) formalizer-only tier2_frontier: pass@1 = 1.000, latency p50 = 0.005s, p95 = 0.006s
- V2 (2026-03-28) prover-only tier0_smoke: pass@1 = 1.000, latency p50 = 32.098s, p95 = 46.173s
- V2 (2026-03-28) prover-only agentic_harness overall: pass@1 = 0.615 (8/13), latency p50 = 224.928s, p95 = 310.331s, avg tool calls = 10.46
- V2 (2026-03-28) prover-only agentic_harness provable split: pass@1 = 0.800 (8/10), latency p50 = 212.721s, p95 = 311.433s, avg tool calls = 9.50
- V2 (2026-03-28) prover-only agentic_harness negative split: pass@1 = 0.000 (0/3), latency p50 = 300.123s, p95 = 305.367s, avg tool calls = 13.67
- V2 (2026-03-28) raw-claim end-to-end tier0_smoke: pass@1 = 0.333 (1/3), latency p50 = 305.802s, p95 = 311.818s
- V2 (2026-03-28) raw-claim end-to-end agentic_harness: pass@1 = 0.615 (8/13), latency p50 = 247.744s, p95 = 335.694s
- V2 (2026-03-28) end-to-end negative controls on agentic_harness: 1/3 verified because `ag_neg_wrong_demand` was weakened during formalization

V2 targets: improve raw-claim end-to-end pass@1 to ≥0.667 within 2 weeks.
