# LeanInteract REPL Verification Report

## Environment
- Verification date: 2026-03-28
- lean-interact version: `0.11.1`
- Lean 4 version: `v4.28.0`
- Mathlib commit: `8f9d9cff6bd728b17a24e163c9402775d9e6a365`
- Platform: `macOS 26.3.1 (arm64)`
- Workspace: `lean_workspace/` with LeanEcon preamble modules already built

## Sources
- LeanInteract overview and compatibility: <https://augustepoiroux.github.io/LeanInteract/stable/>
- LeanInteract tactic mode: <https://augustepoiroux.github.io/LeanInteract/stable/user-guide/tactic-mode/>
- LeanInteract performance guidance: <https://augustepoiroux.github.io/LeanInteract/stable/user-guide/performance/>
- Lean REPL protocol examples: <https://github.com/leanprover-community/repl/blob/master/README.md>

## Basic Connectivity

Cold session startup on the first verified run was `25.757s`.

| Check | Latency | Result |
|------|---------|--------|
| `import Mathlib` + `#check Nat.add_comm` | `15.671s` | PASS |
| `import LeanEcon` + `#check @crra_utility` | `25.859s` | PASS |
| `import LeanEcon.Preamble.Macro.PhillipsCurve` + `#check nkpc` | `27.188s` | PASS |

Observations:
- LeanInteract worked with the local Lean `v4.28.0` toolchain and Mathlib workspace.
- LeanEcon preamble imports worked without custom `LEAN_PATH` plumbing.
- `lean_interact.__version__` is not populated in this installation; `importlib.metadata.version("lean-interact")` is the reliable version source.

## Tactic Execution Latencies

Cold session startup on the final tactic run was `15.350s`.
The first warm import in that session took `17.648s`.
`lake env lean` baseline for a trivial theorem compile took `15.237s`.

| Test | Proof State Creation | Hot Tactic Latency | Kernel Verification | Result |
|------|----------------------|--------------------|---------------------|--------|
| Trivial `rfl` proof | `6.4ms` | `0.8ms` | `16.184s` | PASS |
| NKPC `unfold nkpc` | `26.292s` | `1.5ms` | included below | PASS |
| NKPC `ring` | reused prior proof state | `13.8ms` | `17.941s` | PASS |
| CRRA `field_simp` | `25.876s` | `43.7ms` | `40.446s` | PASS |

Key takeaway:
- Once a proof state exists inside a reused server, tactic steps were consistently sub-`50ms`.
- Proof-state creation is still expensive when a new theorem introduces a fresh import prefix or large elaboration workload.
- The architecture win is real, but it comes from reusing a live REPL session per job and paying kernel verification once at the end.

## Failure Handling

| Check | Result |
|------|--------|
| Invalid tactic returns an error without crashing | PASS |
| Impossible theorem is rejected | PASS |
| Server recovers and proves a valid theorem after failures | PASS |

Observed diagnostics:
- Invalid tactic: `unknown tactic`
- Impossible theorem: `unsolved goals` with goal `False`

## Comparison to `lake env lean`

Using the successful hot tactic steps observed above:

| Operation | REPL | `lake env lean` | Speedup |
|-----------|------|-----------------|---------|
| Single tactic | `0.8ms` to `43.7ms` | `15.237s` | `349x` to `19046x` |
| 10-tactic sequence (extrapolated) | `0.008s` to `0.437s` | `152.37s` | `349x` to `19046x` |

Notes:
- The REPL comparison above is for hot tactic execution, not fresh-session imports.
- Final kernel verification remains expensive and should stay as the trust boundary.

## Issues Found
- The previous verification scripts called `AutoLeanServer.close()`, but the installed API exposes context-manager cleanup and `kill()`, not `close()`.
- Two original benchmark examples were invalid for this workspace:
  - `rra` is not defined in `LeanEcon.Preamble.Consumer.CRRAUtility`.
  - The NKPC test used the wrong theorem shape for `nkpc`, whose definition takes four arguments.
- Running scripts directly from `scripts/verify_repl/` required adding the repo root to `sys.path` to import `src`.
- `AutoLeanServer` can restart under memory pressure, which invalidates raw proof-state ids unless proof-state caching is enabled inside the wrapper.

## Workarounds Applied
- Added a thin wrapper in `src/lean/repl.py` that:
  - lazily caches one `LeanREPLConfig` for the workspace,
  - creates one `AutoLeanServer` per session,
  - exposes `run_command`, `start_proof`, `apply_tactic`, `materialize_proof`, `verify_materialized_proof`, and `kill`,
  - records tactic history so proofs can be materialized and kernel-checked once,
  - preserves proof-state continuity internally for proof creation and tactic steps.
- Rewrote the verification scripts to use valid LeanEcon theorems, real `ProofStep` chaining, and one REPL session per theorem job.

## Integration Status
- The prover fast path in `src/prover/harness.py` now uses one LeanInteract session per job for tactic search before falling back to `compile_check`.
- Proof-state caching is internal to `LeanREPLSession`, not a caller-managed workaround.

## Recommendation
**PROCEED**

LeanInteract is viable for LeanEcon v2 on this workspace, and the deterministic prover path now uses a single REPL session per proving job for local tactic search with final trust still anchored in `compile_check` / `lake env lean`.

Important guardrails for the next bundle:
- Keep final trust with `compile_check` / `lake env lean`.
- Do not benchmark fresh-session import time as if it were per-tactic latency.
