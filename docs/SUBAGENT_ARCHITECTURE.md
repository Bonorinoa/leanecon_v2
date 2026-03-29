**To: CTO**
# LeanEcon v2 — Runtime Subagent Architecture

## Overview

The formalizer and prover currently make direct LLM calls without decomposition.
SOTA systems (APOLLO, AlphaProof, MA-LoT, LeanDojo) achieve better results by splitting work across specialized subagents and utilizing incremental environment state-tracking. With the integration of `lean-interact`, our architecture now supports caching and branching from intermediate nodes (`PickleProofState` / `UnpickleProofState`), shifting us from linear generation to tree search.

This document specifies the subagent architectures for LeanEcon v2's next iteration.

## Design Principle

Subagents are INTERNAL to the API request lifecycle. They are not user-facing
endpoints. They are specialized LLM calls (potentially to cheaper models) that
assist the primary formalizer or prover agent.

## Formalizer Subagents

### 1. Research Assistant ### 1. Research Assistant ### 1. Research Assistant ### 1. Research A** Gather structured context that the formalizer prompt consumes
**Current analog:** src/search/engine.py (deterministic only)

What it would do:
- Take the raw claim text.
- Query Mathlib for relevant lemmas using semantic search (not just keywords).
- Check preamble definitions for type signatures.
- Look up similar formalized claims in the eval history.

### 2. Faithfulness Checker Subagent

**When:** After the formalizer generates a theorem stub
**Purpose:** Verify that the theorem captures the claim's intent
**Current analog:** check_semantic_faithfulness() (heuristic, no LLM)

What it would do:
- Evaluate dropped constraints, weakened conclusions, or added assumptions.
- Catch negative controls before wasting prover compute.

### 3. Assumption Extractor Subagent

**When:** After formalization succeeds
**Purpose:** Identify implicit assumptions the formalizer added
**Current analog:** None

What it would do:
- Expose differences between explicit requirements and formalized hypotheses for the `/api/v2/analyze` endpoint.

## Prover Subagents (LeanInteract Enabled)

### 4. Proof Sketcher (Informal-to-Formal Planner)

**When:** Before the Prover's main tactic loop begins.
**Purpose:** Create a high-level strategic roadmap reducing the search space.
**Current analog:** Prompt-level "think step-by-step"

What it would do:
- Reads the formalized theorem and dependencies.
- Generates an informal outline/proof sketch in natural language.
- Guides the tree-search to prioritize tactics aligning with the sketch.

### 5. Node Evaluator (State Value Scorer)

**When:** During tree-search branching (LeanInteract `PickleProofState`).
**Purpose:** Score nodes to guide Monte Carlo Tree Search (MCTS) or HyperTree search.
**Current analog:** None

What it would do:
- A fast, cheap inference call (e.g., Mistral Small).
- Analyzes the current `lean-interact` proof state and predicts a scalar score (0.0 - 1.0) of its provability.
- Instructs the Prover when to abandon a dead branch and `UnpickleProofState` to an earlier promising node.

### 6. Dynamic Premise Retriever (Prover-side RAG)

**When:** Triggered by the Prover when encountering a novel/stuck goal state.
**Purpose:** Retrieve lemmas tailored strictly to the *current intermediate state*, not just the original claim.
**Current analog:** None

What it would do:
- Translates the active Lean goal state into a query.
- Retrieves theorems from Mathlib or `Preamble/` that unify specifically with the sub-goal.

### 7. Goal Analyst Subagent

**When:** Deep/stuck in the proving loop.
**Purpose:** Provide domain-specific strategy hints.
**Current analog:** None

What it would do:
- Recognizes structural patterns in the Lean goal state (topological, ring algebra, etc.).
- Recommends macro tactics (e.g., "This is an algebraic identity after unfolding. Try `unfold + field_simp + ring`").

### 8. Syntax Fixer Subagent

**When:** Tactic fails with a localized error.
**Purpose:** Sub-millisecond repair of simple misalignments.
**Current analog:** Formalizer repair buckets.

What it would do:
- Deterministic regex fixes, or targeted cheap LLM calls on Lean error outputs.

## Subagent Integration Pattern

Raw Claim 
→ [Research Assistant] → enriched context
→ Formalizer (main LLM) → theorem stub
→ [Faithfulness Checker] → warning or pass
→ [Proof Sketcher] → strategic rough proof
→ Prover (MCTS tool-use loop with `lean-interact` REPL)
  ├── apply_tactic → REPL
  ├── branch / unpickle state → REPL
  ├── [Node Evaluator] → tree pruning
  ├── [Dynamic Premise Retriever] → sub-goal RAG
  ├── [Goal Analyst] → strategic pivot
  └── [Syntax Fixer] → tactical repair
→ Final Verification (`lake env lean`)

## Cost Model (per claim)

| Agent | Model | Calls per request | Estimated cost |
|-------|-------|-------------------|----------------|
| Formalizer (main) | Leanstral | 1-2 | $0.05-0.10 |
| Research / Faithfulness | Small / Cheap | 1-2 | $0.03 |
| Proof Sketcher | Gemini 3.1 / Claude | 1 | $0.05 |
| Prover (main MCTS) | Leanstral | 10-40 | $0.50-2.00 |
| Node Evaluator | Mistral Small | ~10-20 | $0.05-0.10 |
| RAG / Analyst / Fixer | Small | 0-5 | $0.03 |
| **Total per claim** | | | **$0.71-2.31** |

## Implementation Priority

1. **Node Evaluator** (Unlocks true MCTS routing on top of `lean-interact`).
2. **Proof Sketcher** (Improves Prover precision immediately).
3. **Dynamic Premise Retriever** (Reduces hallucinated premises mid-proof).
4. Goal Analyst / Syntax Fixer (Optimizations).

## Relationship to Paperclip

These runtime subagents execute in milliseconds/seconds within the API lifecycle. Paperclip operational agents (see PAPERCLIP_SETUP.md) run asynchronously overnight to autonomously tune the internal prompts and heuristics of these runtime subagents.
