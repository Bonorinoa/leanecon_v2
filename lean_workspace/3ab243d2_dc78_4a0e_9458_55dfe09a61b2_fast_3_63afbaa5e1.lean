import Mathlib
import LeanEcon.Preamble.Producer.ProfitFunction

theorem ag_profit_zero_breakeven
    (p w A α x : ℝ)
    (hbreak : p * (A * Real.rpow x α) = w * x) :
    profit p w A α x = 0 := by
  simp