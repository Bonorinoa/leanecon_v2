import Mathlib
import LeanEcon.Preamble.Macro.PhillipsCurve

theorem ag_nkpc_zero_gap
    (β π_next κ : ℝ) :
    nkpc β π_next κ 0 = β * π_next := by
  rfl