import Mathlib
import LeanEcon.Preamble.Consumer.MarshallianDemand

theorem ag_walras_law
    (α m p₁ p₂ : ℝ)
    (hp₁ : p₁ ≠ 0) (hp₂ : p₂ ≠ 0) :
    marshallian_demand_good1 α m p₁ * p₁ +
    marshallian_demand_good2 α m p₂ * p₂ = m := by
  ring