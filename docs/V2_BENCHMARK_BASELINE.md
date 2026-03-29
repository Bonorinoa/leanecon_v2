# LeanEcon v2 — Benchmark Baseline

**Date:** 2026-03-28
**Branch:** `main`
**Purpose:** First honest benchmark including `agentic_harness`

All metrics below are transcribed from the canonical JSON artifacts in `.cache/evals/`.

## Environment

- Lean 4: `v4.28.0`
- Provider: Mistral `labs-leanstral-2603`
- Python tests: `36 passed`

## Formalizer-Only

| Claim Set | Claims | pass@1 | Latency p50 | Latency p95 |
|-----------|--------|--------|-------------|-------------|
| tier0_smoke | 3 | 1.000 | 0.006s | 0.008s |
| tier1_core | 6 | 1.000 | 0.006s | 0.007s |
| tier2_frontier | 3 | 1.000 | 0.005s | 0.006s |

## Prover-Only

Overall `agentic_harness`: `8/13` stubs proved, `pass@1=0.615`, latency `p50=224.928s`, `p95=310.331s`, average tool calls `10.46`.

| Claim Set | Claims | pass@1 | Latency p50 | Latency p95 | Avg Tool Calls |
|-----------|--------|--------|-------------|-------------|----------------|
| tier0_smoke | 3 | 1.000 | 32.098s | 46.173s | 0.00 |
| agentic_harness (provable) | 10 | 0.800 | 212.721s | 311.433s | 9.50 |
| agentic_harness (negative) | 3 | 0.000 | 300.123s | 305.367s | 13.67 |

## End-to-End

| Claim Set | Claims | pass@1 | Latency p50 | Latency p95 |
|-----------|--------|--------|-------------|-------------|
| tier0_smoke | 3 | 0.333 | 305.802s | 311.818s |
| agentic_harness | 13 | 0.615 | 247.744s | 335.694s |

## Agentic Harness Detail

| Stub ID | Result | Latency | Tool Calls | Notes |
|---------|--------|---------|------------|-------|
| ag_walras_law | pass | 225.1s | 8 | Closed after unfolding both Marshallian demand definitions and simplifying the algebra. |
| ag_nkpc_zero_gap | pass | 224.9s | 11 | Closed after specializing `nkpc` at zero output gap and normalizing the identity. |
| ag_expected_payoff_pure_row | pass | 199.8s | 15 | Prover-only passed, but end-to-end later failed because the formalizer emitted a generic `claim : Prop` theorem instead of the payoff identity. |
| ag_rra_from_ara | pass | 215.3s | 18 | Cross-preamble unfolding succeeded after a longer tool loop. |
| ag_profit_zero_breakeven | fail | 304.7s | 9 | Timed out prover-only, but the corresponding raw claim did verify end-to-end after formalization. |
| ag_budget_set_cheaper_bundle | pass | 174.7s | 6 | Provider handled unfolding at both the hypothesis and goal and closed the inequality reasoning. |
| ag_bellman_linear_utility | pass | 45.4s | 0 | Fast path solved it immediately. |
| ag_present_value_one_period | fail | 316.9s | 17 | Timed out on the direct stub; the end-to-end trace got stuck on algebra around `(1 - β)` and missing/non-discharged side conditions. |
| ag_solow_steady_state_condition | pass | 33.5s | 0 | Fast path solved it immediately after matching the steady-state hypothesis. |
| ag_income_elasticity_unit | pass | 210.1s | 11 | Prover-only passed; end-to-end later reduced the goal to `m = q` but failed to use `h_demand : q = m` before timing out. |
| ag_neg_false_arithmetic | fail | 230.8s | 10 | Correctly rejected overall, but only after a full failure path rather than an early impossibility stop. |
| ag_neg_wrong_demand | fail | 300.1s | 4 | Correctly failed prover-only; end-to-end formalization weakened the claim to `marshallian_demand_good1_simple`, which then verified. |
| ag_neg_division_by_zero | fail | 306.0s | 27 | Timed out after a long search; the end-to-end trace reached `x = 0 ∨ T = 0`, confirming the false `β = 1` claim. |

## Failure Analysis

- `ag_expected_payoff_pure_row`: prover-only succeeded, but end-to-end failed because the formalizer produced `theorem in_a_2x2_game_when_the_row_player (claim : Prop) : claim := by exact?`. The verifier then spent its budget trying to prove an arbitrary proposition and timed out.
- `ag_profit_zero_breakeven`: prover-only timed out after `9` tool calls, while end-to-end later completed on the formalized theorem. This points to direct-stub search weakness rather than a missing capability in the prover.
- `ag_present_value_one_period`: the end-to-end formalizer dropped the original `β ≠ 1` side condition and emitted `theorem present_value_constant_one_period (x β : ℝ) : present_value_constant x β 1 = x`. The trace unfolded the definition and got stuck on `x * (1 - β) / (1 - β) = x`, then timed out.
- `ag_income_elasticity_unit`: after `unfold income_elasticity` and `field_simp`, the verifier reduced the goal to `m = q` with `h_demand : q = m` in context, but never applied the final symmetry/rewrite step before timeout.
- `ag_neg_false_arithmetic`: prover-only ended as a failed verification and end-to-end again timed out. The trace showed `norm_num` reducing the theorem to `False`, but the loop kept searching instead of terminating cleanly on impossibility.
- `ag_neg_wrong_demand`: this is the clearest end-to-end correctness leak. The impossible raw claim was formalized into `theorem marshallian_demand_good1_simple (m p₁ : ℝ) ... : marshallian_demand_good1 1 m p₁ = m / p₁`, fixing `α = 1` and deleting the contradictory `α ≠ 1` premise. That weakened theorem then verified successfully.
- `ag_neg_division_by_zero`: the end-to-end trace on `present_value_constant_discount_one` unfolded the definition and reached the residual goal `x = 0 ∨ T = 0`, which is exactly the obstruction expected from the `β = 1` negative control.
- `t0_one_plus_one` and `t0_budget_constraint`: corrected end-to-end smoke runs also exposed formalizer drift. Both raw claims were translated into generic theorems of the shape `(claim : Prop) : claim`, and both timed out in verification. Only `t0_budget_set_membership` preserved a specific statement and verified.

## Key Findings

- The flattering fast-path numbers remain intact on formalizer-only and prover-only `tier0_smoke`, but corrected raw-claim end-to-end on `tier0_smoke` is only `1/3`.
- The first honest agentic prover baseline is `8/13` overall, with `8/10` success on provable stubs and `0/3` success on negative controls.
- End-to-end `agentic_harness` also lands at `8/13`, but that includes one negative control that verified only because the formalizer weakened the claim. On the raw provable claims alone, end-to-end is `7/10`.
- The dominant bottleneck is theorem shaping, not Lean execution. The strongest failures come from raw claims being formalized into generic `claim : Prop` placeholders or into materially weaker theorems.
- On the prover side, the remaining misses are mostly last-mile reasoning failures: discharging side conditions such as `β ≠ 1`, exploiting simple equalities such as `q = m`, and recognizing impossibility early enough to avoid burning the full timeout budget.
