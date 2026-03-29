# LeanEcon v2 — Roadmap

**Last updated:** 2026-03-29
**Status:** Alpha — REPL integration complete, awaiting benchmark validation
**Architecture:** LeanInteract REPL for proof search + lake env lean for kernel trust

---

## Strategic Context

LeanEcon v2 has proven its core thesis: a provider-agnostic agentic prover can
formally verify economics claims with integrity guardrails that prevent
silent claim weakening.

The Day 1 sprint achieved two major milestones:
1. **Formalizer integrity** — guardrails reject vacuous theorems and flag
   unfaithful formalizations. Tier0 e2e recovered from 0.333 to 1.000.
   All negative controls blocked.
2. **REPL integration** — LeanInteract verified at 0.8-43.7ms per tactic
   step (vs 2-10s per step via file compilation). PROCEED verdict issued.

The file-compilation baseline is now recorded: agentic harness prover
pass@1 = 0.800, latency p50 = 212.7s. The REPL-backed benchmark is the
next number to produce.

---

## Phase 1: Integrity & Baseline — COMPLETE ✅

- [x] v2 repository scaffold with provider-agnostic architecture
- [x] ProverDriver and FormalizerDriver protocols with registry
- [x] Mistral driver (live-tested with Leanstral)
- [x] Gemini driver (mock-tested, ready for live validation)
- [x] SQLite-backed job store with SSE pub/sub
- [x] Agentic harness eval set (13 stubs: 10 provable, 3 negative controls)
- [x] First live benchmark: prover pass@1 = 0.800, e2e pass@1 = 0.615
- [x] Formalizer guardrails (vacuous rejection, faithfulness check)
- [x] Timeout path fix with structured partial results
- [x] Prover "think lemma-by-lemma" prompt enhancement
- [x] Technical paper skeleton (docs/PAPER.md + LaTeX companion)
- [x] Autoresearch experiment 001 (DISCARD — composite fast-path)
- [x] LeanInteract REPL integration (PROCEED verdict)
- [x] Paperclip installed, company structure designed
- [x] Repo simplification: frontend/dashboard artifacts removed from v2

---

## Phase 2: REPL Benchmark & Deployment (Day 2, March 30)

### 2.1 REPL-Backed Benchmark (highest priority)
Run the full eval suite with REPL-backed proving enabled:
- Agentic harness prover-only (the comparison number)
- Tier0 smoke (regression check)
- End-to-end on both sets
- Record as the REPL baseline in V2_BENCHMARK_BASELINE.md
- Compare latency p50/p95 against the 212.7s file-compilation baseline

### 2.2 External Frontend Integration
Keep v2 focused on backend delivery while the user-facing app lives elsewhere:
- Lovable or another external frontend should call the published API directly
- Keep the repo focused: API + Lean workspace + evals + docs + tests
- Avoid reintroducing repo-local dashboard or demo UI code

### 2.3 v1 vs v2 Comparison
Run identical claims through both v1 (Railway deployment) and v2 (local):
- Document differences in formalization quality, proving success, latency
- Use tier1_core claims as the comparison set
- This validates the v2 architecture against the production baseline

### 2.4 Railway Deployment
Deploy v2 skeleton to Railway (new project, separate from v1):
- /health, /api/v2/search, /api/v2/compile live immediately
- /formalize and /verify after REPL benchmark confirms the architecture
- Production smoke test against live URL

### 2.5 Paperclip with Ollama
Configure Paperclip operational agents using local Ollama models:
- Avoids API costs and rate limits for autoresearch cycles
- CEO, FormalizerResearcher, ProverResearcher, EvalRunner agents
- Gate activation on REPL benchmark confirmation

---

## Phase 3: Optimization & Scale (Week of March 31)

### 3.1 APOLLO-Style Sub-Lemma Isolation
With fast REPL feedback, implement the APOLLO pattern:
- LLM generates a complete proof sketch
- Deterministic agents analyze which steps fail
- Automated solvers try each failing subgoal independently
- LLM re-invoked only on subgoals solvers couldn't close

### 3.2 Runtime Subagents (from SUBAGENT_ARCHITECTURE.md)
Implementation priority:
1. Goal Analyst — reduces wasted tool calls during proving
2. Faithfulness Checker — LLM-backed version of the heuristic
3. Proof Sketcher — informal plan before tactic loop
4. Syntax Fixer — deterministic repair of simple tactic errors
5. Node Evaluator — MCTS-compatible state scoring (longer term)

### 3.3 Autoresearch Ratchet Automation
- Connect Paperclip agents to the ratchet loops in PROGRAM.md
- FormalizerResearcher optimizes prompts.py and hints.py
- ProverResearcher optimizes prover prompts and fast_path
- Run overnight cycles with human PR review gates

### 3.4 Preamble Library Expansion
High-priority additions:
- Walrasian equilibrium, Pareto efficiency, Nash equilibrium
- Slutsky equation, DSGE baseline, Euler equation
- Each requires: Lean definition + compilation + keyword metadata + human PR

### 3.5 Provider Diversification
- Live-test Gemini 3.1 Pro driver
- Implement HuggingFace Inference API driver for self-hosted Leanstral
- A/B test providers on cost per verified theorem

---

## Scope Exclusions (explicit)

- **Repo-local frontend or dashboard code** — keep clients separate and use the
  published API plus CLI eval artifacts instead
- **DocProcessor / OCR** — separate product
- **Domain fine-tuning** — insufficient data at current scale
- **LeanCopilot / IDE integration** — we are an API
- **Embedding-based search** — keyword search is sufficient for now

---

## Key References

- **LeanInteract:** Poiroux et al., 2025. Python interface for Lean 4 REPL.
- **APOLLO:** Ospanov et al., NeurIPS 2025. Model-agnostic agentic proving.
- **MA-LoT:** Multi-agent Long CoT for Lean 4.
- **Karpathy autoresearch:** Ratchet pattern for agent-driven optimization.
- **Leanstral:** Mistral, March 2026. First open-source Lean 4 code agent.
- **Refine.ink:** Golub et al. LLM-based economics referee (heuristic, no kernel).

---

## Competitive Position

LeanEcon occupies a unique niche: the only formal verification system targeting
economics specifically. Refine.ink provides heuristic critique (powerful but
stochastic). LeanEcon provides kernel-verified proofs (deterministic but
narrower scope). The two are complementary.

With the REPL integration, LeanEcon's proving architecture is now competitive
with SOTA systems on the Lean interaction layer. The preamble library (29
compiled modules across 8 economics domains) is the defensible asset that
no other project has.
