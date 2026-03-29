import Mathlib
import LeanEcon.Preamble.GameTheory.ExpectedPayoff

theorem ag_expected_payoff_pure_row
    (u₁₁ u₁₂ u₂₁ u₂₂ q : ℝ) :
    expected_payoff_2x2 u₁₁ u₁₂ u₂₁ u₂₂ 1 q =
    q * u₁₁ + (1 - q) * u₁₂ := by
  exact?