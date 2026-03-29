# LeanEcon: Formal Verification of Mathematical Economics Claims via Agentic Theorem Proving

## Abstract

LeanEcon is a provider-agnostic formal verification API for mathematical economics claims that separates deterministic retrieval, stochastic theorem generation, and kernel-checked proof validation into explicit stages. The system uses a three-layer trust model in which language models propose statements and proofs, human reviewers inspect intermediate artifacts when needed, and the Lean 4 kernel acts as the final arbiter of correctness. Current benchmark placeholders indicate that the platform is already suitable for reporting formalizer, prover, end-to-end, and agentic-harness results once the next benchmark sweep is ingested from `.cache/evals/` `[PLACEHOLDER: headline pass@1 result and benchmark date]`.

## 1. Introduction

### 1.1 Motivation

Mathematical economics still relies heavily on prose arguments, textbook lemmas, and informal derivations that are difficult to audit at scale. Formal verification offers a way to convert those arguments into machine-checkable objects, but the manual cost of encoding assumptions, imports, and proof structure in a theorem prover remains high. This section will motivate LeanEcon as a bridge between economist-facing natural language and proof assistant-facing formal statements, with emphasis on reducing verification cost without weakening trust.

### 1.2 Contributions

This paper will claim four main contributions. First, LeanEcon packages an economics-specific preamble library that exposes reusable definitions and lemmas across consumer theory, producer theory, macroeconomics, risk, welfare, optimization, dynamics, and game theory. Second, it introduces an agentic proving architecture with explicit tool budgets and rollback points; third, it keeps the runtime provider-agnostic through stable driver interfaces; and fourth, it ships with an autoresearch-compatible evaluation framework that supports ratcheted improvement rather than one-off demos.

## 2. Related Work

### 2.1 Theorem Proving and Autoformalization

Recent work on theorem proving and autoformalization has shown that large models can contribute meaningfully to formal reasoning pipelines, especially when coupled to proof assistants and tool use `[@alphaproof; @dsp; @proveragent; @lean4; @mathlib]`. This section will position LeanEcon relative to general-purpose theorem-proving systems, emphasizing that the core research question here is not raw olympiad-style proving but domain-specific verification of economics claims. It will also explain why Lean 4 and Mathlib are the relevant substrate for a system that must balance expressivity, engineering velocity, and kernel-level trust.

### 2.2 Economics and Formal Methods

Economics has comparatively little domain-specific infrastructure for machine-checked formalization, even though the field depends on results about optimization, equilibrium, comparative statics, and dynamic systems. Existing formal methods work in neighboring mathematical domains provides inspiration, but there is still no widely used economics-native verification stack with reusable preambles, theorem-stub generation, and an explicit claim-to-proof API. This section will sharpen that gap and describe LeanEcon as a response to the lack of economics-oriented formal tooling.

### 2.3 Agentic Coding and Autoresearch

Agentic coding systems have made it practical to treat prompt tuning, tool use, and benchmark ratcheting as continuous engineering loops rather than isolated experiments `[@karpathy_autoresearch]`. LeanEcon adopts that framing directly: the formalizer and prover are optimized under fixed budgets, measured against stable claim sets, and only retained when the benchmark ratchet improves. This section will connect LeanEcon to the broader autoresearch pattern, where agent-driven systems improve by iterating on measurable intermediate objectives.

## 3. System Architecture

### 3.1 Three-Layer Trust Model

LeanEcon is organized around a three-layer trust model: stochastic model output, optional human-in-the-loop review, and deterministic kernel checking. The important design choice is that only the final layer is authoritative; the earlier layers are convenience and productivity layers that produce candidate artifacts. A system diagram in the full paper will show claims flowing from natural language to theorem stubs to proof attempts, with trust increasing as artifacts move closer to Lean verification.

### 3.2 API Contract

The public API separates retrieval, formalization, compilation, verification, explanation, metrics, and job inspection into nine explicit endpoints. This split matters because `/api/v2/verify` proves only the theorem it is given, while `/api/v2/formalize` is responsible for statement generation and scoped retrieval. The paper will use this section to argue that explicit endpoint boundaries improve auditability, reproducibility, and failure analysis compared with monolithic “prove this claim” interfaces.

### 3.3 Provider-Agnostic Driver Interface

LeanEcon keeps model providers behind `FormalizerDriver` and `ProverDriver` protocols, with registry-based lookup and adapter isolation in the driver layer. That makes the system resilient to provider churn and lets experiments change prompt strategy or budget policy without rewriting the API surface. This section will also describe how the current Mistral-backed implementation can be treated as one concrete backend rather than the system definition itself.

### 3.4 Preamble Library

The current LeanEcon preamble library exposes 23 reusable entries across 8 domains, backed by compiled Lean modules and a keyword-ranked retrieval layer. Those modules supply economics-specific definitions and reusable lemmas that would otherwise have to be reconstructed repeatedly during formalization and proof search. This section will document the library as a domain bridge: it narrows the gap between economics vocabulary and Lean syntax while preserving explicit imports and transparent matching.

## 4. Methodology

### 4.1 Formalization Pipeline

The formalization pipeline starts with deterministic search, then shapes a prompt with retrieved context, generates candidate theorem stubs, validates them, and retries under a bounded repair loop when necessary. The output is bucketed into scope classes such as `IN_SCOPE`, `NEEDS_DEFINITIONS`, and `RAW_LEAN`, which allows downstream analysis to separate “bad claim fit” from “bad statement construction.” This section will explain why statement quality is evaluated before proof search and why theorem-stub validity is an independent research target.

### 4.2 Agentic Proving Loop

The proving loop combines local fast-path tactics with a provider-backed tool-using harness that can read code, compile current state, search retrieval hints, and rewrite the working theorem file under budget constraints. Each verification run tracks tool usage, keeps checkpoints, and can fail with structured metadata instead of opaque timeouts. This section will emphasize that the agentic loop is designed for observability as much as for proof success, because benchmark-driven improvement depends on seeing where and why the loop gets stuck.

### 4.3 Evaluation Framework

LeanEcon evaluates four distinct surfaces: formalizer-only, prover-only, end-to-end, and an agentic harness that forces multi-step proving behavior. Each runner writes JSON artifacts to `.cache/evals/`, emits live progress, and is intended to support ratcheted improvement under fixed time and budget constraints. This section will define the ratchet criteria, summarize the fixed claim sets, and explain why comparing isolated stages is necessary to diagnose system regressions correctly.

## 5. Results

### 5.1 Formalizer Performance

The formalizer results table will report pass@1, latency, and attempt statistics for the smoke, core, and frontier tiers. The current placeholder values indicate that the formalizer is already benchmarked across multiple difficulty bands, but the paper draft intentionally leaves benchmark-sensitive numbers unresolved until they are read directly from artifacts. The narrative here will interpret whether gains come from better statement shaping, better retrieval, or both.

<!-- Source artifacts: .cache/evals/formalizer_only_tier0_smoke.json, .cache/evals/formalizer_only_tier1_core.json, .cache/evals/formalizer_only_tier2_frontier.json -->
| Claim Set | pass@1 | Latency p50 (s) | Latency p95 (s) | Mean Attempts |
| --- | --- | --- | --- | --- |
| tier0_smoke | [PLACEHOLDER: pass@1] | [PLACEHOLDER: p50] | [PLACEHOLDER: p95] | [PLACEHOLDER: attempts mean] |
| tier1_core | [PLACEHOLDER: pass@1] | [PLACEHOLDER: p50] | [PLACEHOLDER: p95] | [PLACEHOLDER: attempts mean] |
| tier2_frontier | [PLACEHOLDER: pass@1] | [PLACEHOLDER: p50] | [PLACEHOLDER: p95] | [PLACEHOLDER: attempts mean] |

### 5.2 Prover Performance

The prover section will separate fast-path wins from cases that require the agentic harness, because those modes have different latency and cost profiles. In the final paper this table will also summarize tool-call behavior, showing whether improvements come from better proof selection or simply from spending more budget. The intended analysis is not just “did it prove the theorem,” but “how expensive was the proof trajectory and what tools were used along the way.”

<!-- Source artifacts: .cache/evals/prover_only_tier0_smoke.json, .cache/evals/prover_only_agentic_harness.json -->
| Claim Set | pass@1 | Latency p50 (s) | Latency p95 (s) | Mean Tool Calls | Max Tool Calls |
| --- | --- | --- | --- | --- | --- |
| tier0_smoke | [PLACEHOLDER: pass@1] | [PLACEHOLDER: p50] | [PLACEHOLDER: p95] | [PLACEHOLDER: mean tool calls] | [PLACEHOLDER: max tool calls] |
| agentic_harness | [PLACEHOLDER: pass@1] | [PLACEHOLDER: p50] | [PLACEHOLDER: p95] | [PLACEHOLDER: mean tool calls] | [PLACEHOLDER: max tool calls] |

### 5.3 End-to-End Performance

End-to-end evaluation measures the complete path from raw claim to verified theorem, which makes it the most user-facing metric in the paper. This section will highlight where end-to-end failures come from: statement generation mistakes, missing formal definitions, or proof-search failures after a plausible stub is already available. It will also compare the end-to-end curve with the formalizer-only and prover-only results to show whether the system is bottlenecked by front-end or back-end behavior.

<!-- Source artifacts: .cache/evals/e2e_tier0_smoke.json, .cache/evals/e2e_agentic_harness.json -->
| Claim Set | pass@1 | Formalize Success Rate | Verify Success Rate | Latency p50 (s) |
| --- | --- | --- | --- | --- |
| tier0_smoke | [PLACEHOLDER: pass@1] | [PLACEHOLDER: formalize rate] | [PLACEHOLDER: verify rate] | [PLACEHOLDER: p50] |
| agentic_harness | [PLACEHOLDER: pass@1] | [PLACEHOLDER: formalize rate] | [PLACEHOLDER: verify rate] | [PLACEHOLDER: p50] |

### 5.4 Agentic Harness Results

The agentic harness is the key stress test for the proving loop because it includes both genuinely provable multi-step stubs and negative controls that should fail clearly. This section will summarize per-stub outcomes, identify the most common failure stages, and note whether the harness is spending budget effectively or thrashing. It will also serve as the main before-versus-after lens for autoresearch ratchets in later revisions.

<!-- Source artifacts: .cache/evals/prover_only_agentic_harness.json, .cache/evals/e2e_agentic_harness.json -->
| Stub Group | Successes | Failures | Dominant Error Type | Notes |
| --- | --- | --- | --- | --- |
| Provable stubs | [PLACEHOLDER: successes] | [PLACEHOLDER: failures] | [PLACEHOLDER: dominant error type] | [PLACEHOLDER: short analysis] |
| Negative controls | [PLACEHOLDER: successes] | [PLACEHOLDER: failures] | [PLACEHOLDER: dominant error type] | [PLACEHOLDER: short analysis] |

## 6. Discussion

### 6.1 Statement Quality as the Primary Bottleneck

One likely conclusion of the final paper is that theorem-stub quality dominates downstream proof performance once the prover is given a clean target. Even strong proof search degrades rapidly when quantifiers, domains, or imports are underspecified in the formalization stage. This subsection will therefore argue that autoformalization quality is not a pre-processing detail but the central systems bottleneck.

### 6.2 The Unfold Barrier for Noncomputable Definitions

LeanEcon’s economics preambles often rely on noncomputable definitions, which creates a recurring “unfold barrier” before algebraic tactics become useful. The agentic harness is designed in part to make that barrier visible, because one-step tactics can fail even on otherwise simple theorems when the relevant definitions remain opaque. This section will discuss the engineering and scientific implications of that barrier for fast-path design.

### 6.3 Cost-Performance Tradeoffs Across Providers

Because the driver interface is provider-agnostic, LeanEcon is positioned to compare proof quality, latency, and cost across backend models without rewriting the core system. The paper will use this subsection to frame provider choice as an optimization problem over pass@1, tool efficiency, and latency rather than a branding decision. That makes LeanEcon a useful benchmark harness as well as an application system.

### 6.4 Limitations

LeanEcon does not eliminate the need for human judgment about theorem scope, modeling assumptions, or economic interpretation. The current benchmark sets are still relatively small, the preamble library is incomplete, and the system presently emphasizes claim verification rather than automatic assumption discovery. This subsection will make those limits explicit so that later benchmark improvements are interpreted as scoped progress rather than complete automation.

## 7. Future Work

Future work will extend the autoresearch ratchet to larger claim suites, tighter experiment bookkeeping, and richer comparisons between providers and prompting strategies `[@karpathy_autoresearch; @leanstral]`. Additional directions include Paperclip-style orchestration for research workflows, expansion of the economics preamble library, automatic assumption extraction from prose claims, and a pedagogical tutor that explains verified proofs back to economists. This section will position LeanEcon as both a verification API and a research instrument for studying how agentic formal methods improve over time.

## 8. Conclusion

LeanEcon is best understood as an explicit systems architecture for turning economics claims into auditable, machine-checkable verification artifacts. Its central claim is that stochastic generation can be useful without being trusted, so long as the workflow ends in deterministic kernel checking and exposes enough intermediate structure for human review and benchmark ratcheting. The final paper will close by arguing that this combination of explicit APIs, domain preambles, and agentic proof tooling creates a practical path toward trustworthy formal methods in economics.

## References

Bibliography entries for this draft live in `docs/paper/references.bib`. The current citation keys used in the paper skeleton are `alphaproof`, `dsp`, `proveragent`, `lean4`, `mathlib`, `karpathy_autoresearch`, and `leanstral`; their metadata should be verified before submission and kept in sync with the LaTeX companion.
