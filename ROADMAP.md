# Roadmap

## Phase 2A

- Scaffold the repository, runtime skeleton, and public API contract.
- Make `/health` and deterministic `/api/v2/search` operational.
- Keep proving, formalization, compilation, jobs, streaming, explain, and
  metrics routes present but explicitly deferred to Phase 3.

## Phase 2B

- Copy the Lean workspace, preamble entries, claim sets, and skill assets from
  the prior internal codebase.
- Validate that retrieval works against real Lean assets without changing the
  v2 API surface.

## Phase 3

- Implement the formalizer, compile primitive, async verification jobs, and
  provider-backed driver execution.
- Add SSE progress, job persistence, and explanation generation.

## Phase 4

- Run benchmark ratchets, harden deployment, and publish eval artifacts through
  the Hugging Face ecosystem layer.
