# LeanEcon v2 — Roadmap

**Last updated:** 2026-03-29
**Status:** Alpha → approaching beta
**Architecture pivot:** Pantograph integration approved as next major change

---

## Strategic Context

LeanEcon v2 has proven its core thesis: a provider-agnostic agentic prover can
formally verify economics claims. The first honest benchmark (agentic harness,
2026-03-29) showed pass@1 = 0.800 on multi-step proofs and pass@1 = 0.615
end-to-end. The system works.

A research review of the SOTA landscape (APOLLO, MA-LoT, Pantograph, LeanDojo,
Refine.ink) identified a clear architectural bottleneck: our prover interacts
with Lean via full-file recompilation on every tactic attempt (2-10 seconds per
step). SOTA systems use Pantograph or Lean REPL for incremental tactic
execution (~50-200ms per step). This is a 10-100x improvement in Lean
interaction latency, and it unlocks search strategies (MCTS, sub-lemma
isolation) that are infeasible with our current architecture.

The roadmap is therefore organized into three phases:
1. **Integrity & Baseline** (this weekend) — fix the formalizer trust boundary
2. **Pantograph Integration** (next sprint) — the architectural upgrade
3. **Scale & Automate** (ongoing) — autoresearch, preamble expansion, deployment

---

## Phase 1: Integrity & Baseline (March 29-30, 2026)

### Completed ✅
- [x] v2 repository scaffold with provider-agnostic architecture
- [x] ProverDriver and FormalizerDriver protocols with registry
- [x] Mistral driver (live-tested with Leanstral)
- [x] Gemini driver (mock-tested, ready for live validation)
- [x] SQLite-backed job store with SSE pub/sub
- [x] Agentic harness eval set (13 stubs: 10 provable, 3 negative controls)
- [x] First live benchmark: prover pass@1 = 0.800, e2e pass@1 = 0.615
- [x] Timeout path fix with structured partial results
- [x] Prover "think lemma-by-lemma" prompt enhancement
- [x] Technical paper skeleton (docs/PAPER.md + LaTeX companion)
- [x] Eval dashboard (tools/eval_dashboard.jsx)
- [x] Paperclip onboarding (local installation complete)

### In Progress 🔄
- [ ] Formalizer integrity guardrails (vacuous rejection, faithfulness check)
- [ ] First autoresearch ratchet cycle (composite fast-path experiment)
- [ ] v2 demo frontend (React + SSE timeline)

### Remaining
- [ ] Update V2_BENCHMARK_BASELINE.md with post-guardrail numbers
- [ ] Deploy skeleton to Railway (health + search + compile live)

---

## Phase 2: Pantograph Integration (Target: April 1-7, 2026)

### Why Pantograph

The current prover architecture uses `lake env lean` (full-file compilation)
for every tactic attempt. This costs 2-10 seconds per step. For a 10-step
proof, 20-100 seconds are spent just waiting for Lean, regardless of LLM speed.

Pantograph provides a machine-to-machine REPL for Lean 4 that executes
individual tactics incrementally in ~50-200ms. It was designed specifically
for ML-driven proof search, supports goal-state inspection, subgoal branching,
sorry-extraction, and MCTS-compatible tree structures.

### Integration Plan

1. **Add Pantograph as Lean dependency**
   - Add to `lean_workspace/lakefile.toml`
   - Build the REPL executable via `lake build`
   - Verify it runs against our preamble library

2. **Build Python wrapper (`src/lean/repl.py`)**
   - Manage a persistent Pantograph subprocess
   - Expose: `start_proof(expr)`, `apply_tactic(state_id, goal_id, tactic)`,
     `get_goals(state_id)`, `reset()`
   - Handle lifecycle: start on first use, restart on crash, cleanup on shutdown
   - Timeout per-tactic (5 seconds) and per-proof (configurable)

3. **Redesign prover harness tools**
   - Replace `compile_current_code` tool with `get_goal_state` (instant, via REPL)
   - Replace `apply_tactic` tool with REPL-backed tactic execution (instant feedback)
   - Keep `read_current_code` for the LLM to see the full proof so far
   - Keep `lake env lean` as the FINAL verification step only (kernel trust)

4. **Update fast path to use REPL**
   - Single-tactic and composite-tactic attempts via REPL instead of file compilation
   - Reduces fast-path latency from ~30-60 seconds (N compilations) to ~2-5 seconds

5. **Eval and compare**
   - Run all existing evals against the Pantograph-backed prover
   - Compare latency, pass@1, and tool-call efficiency vs file-compilation baseline
   - Record as autoresearch experiment

### Architecture After Pantograph

```
Request → API → Prover Harness
                    ├── Fast Path (Pantograph REPL, ~2s)
                    │   └── If solved → lake env lean final check → done
                    ├── LLM Driver (tool-use loop)
                    │   ├── get_goal_state → Pantograph REPL (~100ms)
                    │   ├── apply_tactic → Pantograph REPL (~100ms)
                    │   └── search_lemma → deterministic search (~50ms)
                    └── Final Verification
                        └── lake env lean (full compilation, 2-10s, ONCE)
```

### Success Criteria
- Prover-only agentic harness latency p50 < 30 seconds (currently ~90s)
- Pass@1 equal or better than file-compilation baseline
- Tool call budget more efficiently used (fewer wasted compilations)
- Final verification still uses lake env lean (kernel trust preserved)

---

## Phase 3: Scale & Automate (Target: April 8+)

### 3.1 APOLLO-Style Sub-Lemma Isolation
Once Pantograph provides fast tactic feedback, implement the APOLLO pattern:
- LLM generates a complete proof sketch
- Deterministic agents analyze which steps fail
- Automated solvers try each failing subgoal independently
- LLM re-invoked only on subgoals solvers couldn't close
- This reduces LLM token usage by 60-80% on multi-step proofs

### 3.2 Autoresearch Automation via Paperclip
- Configure Paperclip agents for formalizer and prover ratchet loops
- FormalizerResearcher: optimize prompts/hints, eval, keep/discard
- ProverResearcher: optimize prover instructions/budget, eval, keep/discard
- Run overnight ratchet cycles with human PR review gates

### 3.3 Preamble Library Expansion
High-priority additions (from research review):
- Walrasian equilibrium definitions
- Pareto efficiency formalization
- Nash equilibrium (finite games)
- Slutsky equation components
- DSGE baseline definitions
- Euler equation formalization

Each entry requires: Lean definition, compilation verification, keyword
metadata for search matching, and human PR approval.

### 3.4 Provider Diversification
- Live-test Gemini 3.1 Pro driver against existing eval sets
- Implement HuggingFace Inference API driver for self-hosted Leanstral
- A/B test providers: compare pass@1 and cost per verified theorem
- Make provider selection a user-facing configuration option

### 3.5 Deployment Hardening
- Railway production deployment with health monitoring
- Lean environment pre-warming strategy for cold starts
- Concurrent request handling (with Pantograph process pool)
- Rate limiting and API key management for public access

### 3.6 Assumption Extraction Feature
- New endpoint: POST /api/v2/analyze
- Takes a raw claim, returns explicit vs implicit assumptions
- Diff between informal claim text and formal theorem hypotheses
- Reveals what the formalizer "added" to make the claim well-typed
- High pedagogical value for economics students

---

## What We Are NOT Building (explicit scope exclusions)

- **DocProcessor / OCR pipeline** — separate product, not v2 scope
- **Domain fine-tuning** — insufficient data and compute at current scale
- **LeanCopilot / IDE integration** — we are an API, not an IDE plugin
- **Embedding-based search** — deterministic keyword search is sufficient
- **Equivalence checking** — requires ground-truth Lean statements we don't have
- **Clipmart company template** — Paperclip marketplace listing is premature

---

## Key References (informing this roadmap)

- **Pantograph:** Aniva et al., TACAS 2025. Machine-to-machine Lean 4 REPL.
- **APOLLO:** Ospanov et al., NeurIPS 2025. Model-agnostic agentic proving, 84.9% on miniF2F.
- **MA-LoT:** Multi-agent Long CoT for Lean 4, 61% on miniF2F.
- **Karpathy autoresearch:** Ratchet pattern for agent-driven optimization.
- **Leanstral:** Mistral, March 2026. First open-source Lean 4 code agent.
- **Refine.ink:** Golub et al. LLM-based economics referee (heuristic, no formal verification).

---

## Competitive Positioning

LeanEcon v2 occupies a unique position: the only formal verification system
targeting economics specifically. Refine.ink provides heuristic critique
(powerful but stochastic). LeanEcon provides kernel-verified proofs
(deterministic but narrower scope). The two are complementary.

With Pantograph integration, LeanEcon's proving architecture will be
competitive with SOTA systems (APOLLO, MA-LoT) while remaining provider-agnostic
and open-source. The preamble library is the defensible asset — no other
project has compiled Lean modules for CRRA, Cobb-Douglas, CES, budget sets,
Phillips curves, or Bellman equations.
