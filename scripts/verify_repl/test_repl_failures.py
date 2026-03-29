"""Bundle 9 verification — Step 3: Failure mode and recovery checks."""

from __future__ import annotations

import sys
from pathlib import Path

from lean_interact.interface import LeanError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lean.repl import LeanREPLSession

TIMEOUT_SECONDS = 60


def _is_invalid(result) -> bool:
    if isinstance(result, LeanError):
        return True
    return not result.lean_code_is_valid()


def _messages(result) -> list[str]:
    if isinstance(result, LeanError):
        return [result.message]
    return [message.data for message in result.messages]


def main() -> bool:
    print("=== LeanInteract Failure Handling ===")
    results = {}

    with LeanREPLSession(timeout=TIMEOUT_SECONDS) as session:
        session.start_proof(
            "import Mathlib\n"
            "theorem invalid_tactic_demo : 1 + 1 = 2 := by\n"
            "  sorry",
            timeout=TIMEOUT_SECONDS,
        )
        invalid_tactic = session.apply_tactic(
            "fake_tactic_that_doesnt_exist",
            timeout=TIMEOUT_SECONDS,
        )
        results["invalid_tactic"] = isinstance(invalid_tactic, LeanError)
        print(
            f"[{'PASS' if results['invalid_tactic'] else 'FAIL'}] "
            "Invalid tactic returns an error without crashing"
        )
        for line in _messages(invalid_tactic):
            print(f"       {line}")

        impossible = session.run_command(
            "import Mathlib\n"
            "theorem impossible_demo : (0 : ℝ) = 1 := by\n"
            "  norm_num",
            timeout=TIMEOUT_SECONDS,
        )
        results["impossible_theorem"] = _is_invalid(impossible)
        print(
            f"[{'PASS' if results['impossible_theorem'] else 'FAIL'}] "
            "Impossible theorem is rejected"
        )
        for line in _messages(impossible):
            print(f"       {line}")

        session.start_proof(
            "import Mathlib\n"
            "theorem recovery_demo : 2 + 2 = 4 := by\n"
            "  sorry",
            timeout=TIMEOUT_SECONDS,
        )
        recovery = session.apply_tactic("norm_num", timeout=TIMEOUT_SECONDS)
        recovery_ok = not isinstance(recovery, LeanError) and not recovery.has_errors()
        kernel_ok = session.verify_materialized_proof(
            filename="bundle9_recovery.lean",
            timeout=TIMEOUT_SECONDS,
        )["success"]
        results["recovery"] = recovery_ok and kernel_ok
        print(
            f"[{'PASS' if results['recovery'] else 'FAIL'}] "
            "Server recovers and kernel verification still succeeds"
        )
        for line in _messages(recovery):
            print(f"       {line}")

    passed = sum(results.values())
    total = len(results)
    print(f"\n{passed}/{total} failure-mode tests passed")
    return passed == total


if __name__ == "__main__":
    import sys

    sys.exit(0 if main() else 1)
