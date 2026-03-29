"""Bundle 9 verification — Step 2: Tactic execution and latency."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from lean_interact.interface import LeanError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lean.compiler import lean_run_code
from src.lean.repl import LeanREPLSession

TIMEOUT_SECONDS = 60


def _messages(result) -> list[str]:
    if isinstance(result, LeanError):
        return [result.message]
    return [message.data for message in result.messages]


def _format_goals(result) -> str:
    if isinstance(result, LeanError):
        return ""
    return " | ".join(result.goals) if getattr(result, "goals", None) else "no goals"


def _run_tactic_case(
    *,
    label: str,
    theorem_with_sorry: str,
    tactics: list[str],
    kernel_filename: str,
) -> tuple[bool, dict[str, float]]:
    timings: dict[str, float] = {}

    with LeanREPLSession(timeout=TIMEOUT_SECONDS) as session:
        started = time.perf_counter()
        proof_state = session.start_proof(theorem_with_sorry, timeout=TIMEOUT_SECONDS)
        timings["proof_state_creation"] = time.perf_counter() - started
        print(
            f"[INFO] {label} proof state ({timings['proof_state_creation']:.3f}s)"
            f" goal={proof_state.goal!r}"
        )

        ok = True
        for index, tactic in enumerate(tactics, start=1):
            started = time.perf_counter()
            result = session.apply_tactic(tactic, timeout=TIMEOUT_SECONDS)
            elapsed = time.perf_counter() - started
            timings[f"tactic_{index}"] = elapsed
            passed = not isinstance(result, LeanError) and not result.has_errors()
            ok = ok and passed
            status = "PASS" if passed else "FAIL"
            proof_status = getattr(result, "proof_status", "LeanError")
            print(
                f"[{status}] {label} tactic {index}: {tactic!r} "
                f"({elapsed*1000:.1f}ms) status={proof_status} goals={_format_goals(result)}"
            )
            for message in _messages(result):
                print(f"       {message}")

        kernel_started = time.perf_counter()
        kernel_check = session.verify_materialized_proof(
            filename=kernel_filename,
            timeout=TIMEOUT_SECONDS,
        )
        timings["kernel_verification"] = time.perf_counter() - kernel_started
    kernel_ok = kernel_check["success"]
    ok = ok and kernel_ok
    status = "PASS" if kernel_ok else "FAIL"
    print(
        f"[{status}] {label} final kernel verification "
        f"({timings['kernel_verification']:.3f}s)"
    )
    if not kernel_ok:
        for line in kernel_check["errors"]:
            print(f"       {line}")

    return ok, timings


def main() -> bool:
    print("=== LeanInteract Tactic Execution & Latency ===")

    cold_started = time.perf_counter()
    with LeanREPLSession(timeout=TIMEOUT_SECONDS) as session:
        cold_start = time.perf_counter() - cold_started
        print(f"Cold session startup: {cold_start:.3f}s")

        warm_started = time.perf_counter()
        warm_result = session.run_command("import Mathlib\n#check Nat.add_comm", timeout=TIMEOUT_SECONDS)
        warm_elapsed = time.perf_counter() - warm_started
        warm_ok = not isinstance(warm_result, LeanError) and warm_result.lean_code_is_valid()
        print(f"[{'PASS' if warm_ok else 'FAIL'}] Warm import path ({warm_elapsed:.3f}s)")

    baseline_started = time.perf_counter()
    baseline = lean_run_code(
        "import Mathlib\ntheorem baseline_demo : 1 + 1 = 2 := by\n  norm_num\n",
        timeout=TIMEOUT_SECONDS,
        filename="bundle9_baseline.lean",
    )
    baseline_elapsed = time.perf_counter() - baseline_started
    baseline_ok = baseline["success"]
    print(
        f"[{'PASS' if baseline_ok else 'FAIL'}] lake env lean baseline "
        f"({baseline_elapsed:.3f}s)"
    )

    results = {}
    timings = {}

    results["rfl"], timings["rfl"] = _run_tactic_case(
        label="Trivial rfl proof",
        theorem_with_sorry=(
            "import Mathlib\n"
            "theorem repl_rfl_demo (n : Nat) : n = n := by\n"
            "  sorry"
        ),
        tactics=["rfl"],
        kernel_filename="bundle9_rfl.lean",
    )
    results["nkpc"], timings["nkpc"] = _run_tactic_case(
        label="NKPC unfold + ring",
        theorem_with_sorry=(
            "import LeanEcon.Preamble.Macro.PhillipsCurve\n"
            "theorem repl_nkpc_demo (β π_next κ x : ℝ) :\n"
            "    nkpc β π_next κ x = β * π_next + κ * x := by\n"
            "  sorry"
        ),
        tactics=["unfold nkpc", "ring"],
        kernel_filename="bundle9_nkpc.lean",
    )
    results["crra"], timings["crra"] = _run_tactic_case(
        label="CRRA field_simp",
        theorem_with_sorry=(
            "import LeanEcon.Preamble.Consumer.CRRAUtility\n"
            "theorem repl_crra_demo (c γ : ℝ) (hc : c > 0) (hγ : γ > 0) (hne : γ ≠ 1) :\n"
            "    -c * (-γ * c⁻¹) = γ := by\n"
            "  sorry"
        ),
        tactics=["field_simp"],
        kernel_filename="bundle9_crra.lean",
    )

    print("\n=== LATENCY SUMMARY ===")
    print(f"Cold startup: {cold_start:.3f}s")
    print(f"Warm import: {warm_elapsed:.3f}s")
    print(f"lake env lean baseline: {baseline_elapsed:.3f}s")
    for label, case_timings in timings.items():
        proof_creation_ms = case_timings["proof_state_creation"] * 1000
        hot_steps_ms = [
            elapsed * 1000 for name, elapsed in case_timings.items() if name.startswith("tactic_")
        ]
        kernel_ms = case_timings["kernel_verification"] * 1000
        print(
            f"{label}: proof_state={proof_creation_ms:.1f}ms, "
            f"hot_steps={[round(value, 1) for value in hot_steps_ms]}, "
            f"kernel_verify={kernel_ms:.1f}ms"
        )

    passed = sum(results.values())
    total = len(results)
    print(f"{passed}/{total} tactic tests passed")
    return warm_ok and baseline_ok and passed == total


if __name__ == "__main__":
    import sys

    sys.exit(0 if main() else 1)
