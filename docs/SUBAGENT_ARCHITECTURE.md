# LeanEcon v2 — Runtime Subagent Architecture

## Overview

The formalizer and prover currently make direct LLM calls without decomposition.
SOTA systems (APOLLO, MA-LoT) achieve better results by splitting work across
specialized subagents. This document specifies the subagent architecture for
LeanEcon v2's next iteration.

## Design Principle

Subagents are INTERNAL to the API request lifecycle. They are not user-facing
endpoints. They are specialized LLM calls (potentially to cheaper models) that
assist the primary formalizer or prover agent.

## Formalizer Subagents

### 1. Research Assistant Subagent

**When:** Before the main formalization LLM call
**Purpose:** Gather structured context that the formalizer prompt consumes
**Current analog:** src/search/engine.py (deterministic only)

What it would do:
- Take the raw claim text
- Query Mathlib for relevant lemmas using semantic search (not just keywords)
- Check preamble definitions for type signatures
- Look up similar formalized claims in the eval history
- Package results as structured context

**Implementation path:**
- Could use a cheaper/faster model (e.g., Mistral Small) for the search query
  formulation, then deterministic Lean REPL for verification
- OR could be a specialized tool in the formalizer's tool kit
- The key is: the research happens BEFORE the expensive formalization call,
  not during it

**Expected impact:** Reduces hallucinated identifiers by providing verified
import paths before the formalizer writes code.

### 2. Faithfulness Checker Subagent

**When:** After the formalizer generates a theorem stub
**Purpose:** Verify that the theorem captures the claim's intent
**Current analog:** check_semantic_faithfulness() (heuristic, no LLM)

What it would do:
- Compare the raw claim against the theorem statement
- Identify dropped constraints, weakened conclusions, or added assumptions
- Use an LLM to assess: "Does this theorem, if proven, actually establish
  what the claim says?"
- Return a structured assessment with confidence score

**Implementation path:**
- Use a different model than the formalizer to avoid self-confirmation bias
- Could be the same model with a different persona/temperature
- The check is cheap (single LLM call, short prompt) relative to the
  formalization itself

**Expected impact:** Catches the negative-control leakage problem at the
source — the system would have rejected ag_neg_wrong_demand before proving.

### 3. Assumption Extractor Subagent

**When:** After formalization succeeds
**Purpose:** Identify implicit assumptions the formalizer added
**Current analog:** None

What it would do:
- Diff the raw claim text against the theorem hypotheses
- For each hypothesis not explicitly stated in the claim, flag it as implicit
- Produce: {"explicit": [...], "implicit": [...], "potential_gaps": [...]}

**Implementation path:** Future /api/v2/analyze endpoint would expose this

## Prover Subagents

### 4. Goal Analyst Subagent

**When:** During the proving loop, when the prover gets stuck
**Purpose:** Analyze the current goal state and suggest a proof strategy
**Current analog:** None (the LLM just retries tactics)

What it would do:
- Read the current Lean goal state (from REPL)
- Identify the mathematical structure (algebraic, topological, inductive, etc.)
- Suggest a high-level strategy: "This is an algebraic identity after unfolding.
  Try unfold + field_simp + ring."
- Recommend specific Mathlib lemmas based on the goal shape

**Implementation path:**
- Could be a cheaper model (Mistral Small) that's fast but good at pattern
  matching on goal structures
- OR could be a deterministic heuristic that maps goal patterns to tactic
  sequences (simpler, faster, no LLM cost)
- Invoked only when the main prover has used N tool calls without progress

**Expected impact:** Reduces wasted tool calls. Instead of the prover blindly
trying tactics, it gets a strategic hint. This is the APOLLO "sub-lemma
isolator" pattern adapted for our architecture.

### 5. Syntax Fixer Subagent

**When:** After a tactic fails with a syntax or type error
**Purpose:** Fix the tactic without re-invoking the expensive main prover
**Current analog:** Repair buckets in formalizer (but not in prover)

What it would do:
- Read the failed tactic and the Lean error message
- Apply deterministic fixes: swap Lean 3 syntax for Lean 4, fix parentheses,
  correct identifier capitalization
- If deterministic fixes don't work, make one targeted LLM call with just
  the error context

**Implementation path:**
- Phase 1: deterministic regex-based fixes (no LLM, sub-millisecond)
- Phase 2: targeted LLM call with minimal context (cheaper model)

## Subagent Integration Pattern
Raw Claim → [Research Assistant] → enriched context
→ Formalizer (main LLM call) → theorem stub
→ [Faithfulness Checker] → warning or pass
→ Prover (tool-use loop with REPL)
├── apply_tactic → REPL
├── get_goals → REPL
└── [Goal Analyst] → strategy hint (on stall)
└── [Syntax Fixer] → tactic repair (on error)
→ Final Verification (lake env lean)

## Cost Model

| Agent | Model | Calls per request | Estimated cost |
|-------|-------|-------------------|----------------|
| Formalizer (main) | Leanstral | 1-2 | $0.05-0.10 |
| Research Assistant | Mistral Small or deterministic | 1 | $0.01 or $0 |
| Faithfulness Checker | Leanstral | 1 | $0.02 |
| Prover (main) | Leanstral | 10-40 tool turns | $0.50-2.00 |
| Goal Analyst | Mistral Small | 0-3 (on stall) | $0-0.05 |
| Syntax Fixer | Deterministic or Small | 0-5 | $0-0.03 |
| **Total per claim** | | | **$0.58-2.20** |

## Implementation Priority

1. Goal Analyst (highest ROI — reduces wasted tool calls during proving)
2. Faithfulness Checker (catches integrity issues the heuristic misses)
3. Syntax Fixer (deterministic phase first, then LLM phase)
4. Research Assistant (after preamble library is larger)
5. Assumption Extractor (product feature, not proving improvement)

## Relationship to Paperclip

These subagents are NOT Paperclip agents. They are runtime code modules
called during API request processing. Paperclip agents operate at a different
timescale — they optimize the system overnight, not during a request.

The connection: Paperclip's autoresearch agents optimize the PROMPTS and
PARAMETERS of these runtime subagents. For example:
- A Paperclip FormalizerResearcher agent might tune the Research Assistant's
  search query templates
- A Paperclip ProverResearcher agent might tune the Goal Analyst's strategy
  selection heuristics
