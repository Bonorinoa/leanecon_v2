# Paper Notes

LeanEcon v2 is designed as a formal verification API for economics claims with
clear separation between stochastic generation and deterministic proof checking.

## Narrative Arc

- Natural-language claims remain useful inputs for economists.
- Formalization and proving benefit from agentic LLM loops.
- Trust comes from Lean kernel verification, not from model confidence.

## What v2 Changes

- Simpler endpoint boundaries.
- Provider-agnostic proving interfaces.
- Explicit research surfaces for prompts, hints, and retrieval tuning.
- Hugging Face reserved for datasets, model registry metadata, and eval
  artifacts rather than runtime execution.
