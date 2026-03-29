import Mathlib
import LeanEcon.Preamble.Consumer.IncomeElasticity

/-- Income elasticity of demand is unity when the demand function is linear in income (q = m). -/
theorem income_elasticity_of_demand_is_unity_when_the
    (m q : ℝ)
    (hm : m ≠ 0) (hq : q ≠ 0)
    (hlinear : q = m) :
    income_elasticity 1 m q = 1 := by
  sorry
