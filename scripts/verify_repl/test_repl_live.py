"""Bundle 9 verification — Step 1: Basic REPL connectivity."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from lean_interact.interface import LeanError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lean.repl import LeanREPLSession

TIMEOUT_SECONDS = 60


def _message_lines(result) -> list[str]:
    if isinstance(result, LeanError):
        return [result.message]
    return [message.data for message in result.messages]


def _run_check(session: LeanREPLSession, label: str, command: str) -> tuple[bool, float]:
    started = time.perf_counter()
    result = session.run_command(command, timeout=TIMEOUT_SECONDS)
    elapsed = time.perf_counter() - started
    ok = not isinstance(result, LeanError) and result.lean_code_is_valid()
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label} ({elapsed:.3f}s)")
    for line in _message_lines(result):
        print(f"       {line}")
    return ok, elapsed


def main() -> bool:
    print("=== LeanInteract Basic Connectivity ===")
    cold_started = time.perf_counter()
    with LeanREPLSession(timeout=TIMEOUT_SECONDS) as session:
        cold_start = time.perf_counter() - cold_started
        print(f"Cold session startup: {cold_start:.3f}s")

        results = {}
        timings = {}

        results["mathlib"], timings["mathlib"] = _run_check(
            session,
            "Import Mathlib + #check Nat.add_comm",
            "import Mathlib\n#check Nat.add_comm",
        )
        results["leanecon"], timings["leanecon"] = _run_check(
            session,
            "Import LeanEcon + #check @crra_utility",
            "import LeanEcon\n#check @crra_utility",
        )
        results["nkpc"], timings["nkpc"] = _run_check(
            session,
            "Import PhillipsCurve + #check nkpc",
            "import LeanEcon.Preamble.Macro.PhillipsCurve\n#check nkpc",
        )

    passed = sum(results.values())
    total = len(results)
    print("\n=== CONNECTIVITY SUMMARY ===")
    print(f"Cold startup: {cold_start:.3f}s")
    for name, elapsed in timings.items():
        print(f"{name}: {elapsed:.3f}s")
    print(f"{passed}/{total} connectivity tests passed")
    return passed == total


if __name__ == "__main__":
    import sys

    sys.exit(0 if main() else 1)
