**To: CTO**
# LeanEcon Paperclip Agent Configuration

## Company Structure

Company: LeanEcon
Board: Augusto (Founder)

### Agents to Create

#### 1. LeaneconCEO
- **Role:** Decompose PROGRAM.md research goals into agent tasks.
- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtime:**- **Runtim prover ratchet loop and optimize MCTS node traversal.
- **Runtime:** Codex 5.4
- **Budget:** $30/month
- **Heartbeat:** Every 4 hours
- **Responsibilities:**
  - Tune the Prompt payloads and HyperTree exploration parameters in `src/prover/`.
  - Run: `python -m evals.prover_only --claim-set agentic_harness`
  - Submit operational improvements as PRs.

#### 4. PreambleHarvester (Data Accumulation)
- **Role:** Expand the Lean economics vocabulary.
- **Runtime:** Sonnet 3.7 / DeepSeek
- **Budget:** $15/month
- **Heartbeat:** Nightly at 02:00
- **Responsibilities:**
  - Read public/standard micro & macro textbooks.
  - Formulate basic definitions and identities (e.g., Slutsky, Cobb-Douglas).
  - Use `src/lean/compiler.py` to ensure valid compilation.
  - Open PRs adding new modules to `lean_workspace/LeanEcon/Preamble/`.

#### 5. CurriculumGenerator (Eval Expansion)
- **Role:** Generate holdout verification tests.
- **Runtime:** Codex 5.4
- **Budget:** $10/month
- **Heartbeat:** Weekly
- **Responsibilities:**
  - Select successfully proven claims from `tier1_core`.
  - Introduce structural variations (e.g., alter constraints, reverse inequalities).
  - Add newly generated claims to JSONL eval sets to prevent Prover over-indexing on `tier0_smoke`.

#### 6. EvalRunner
- **Role:** Execute complete lifecycle benchmark suites.
- **Runtime:** Codex 5.4
- **Budget:** $10/month
- **Heartbeat:** On-demand (merge/CEO-triggered)
- **Responsibilities:**
  - Consolidate all metrics to update `docs/PAPER.md` tables.

### Org Chart
   ┌─────────┐
   │  Board   │ ← Augusto (approves PRs, sets budgets)
   │(Founder) │
   └────┬─────┘
        │
 ┌──────┴──────┐
 │ LeaneconCEO │ ← Reads PROGRAM.md, creates tasks
 └──┬───┬───┬──┴──┬───┬───┐
    │   │   │     │   │   │
┌───┴┐┌─┴─┐┌┴─┐ ┌─┴─┐┌┴──┐┌┴────────┐
│Form││Pro││Pre│ │Cur││Eva││         │
│Rsch││Rsc││Har│ │Gen││Run││         │
└───┘└───┘└───┘ └───┘└───┘└─────────┘

### Governance Rules

- No agent modifies core `lean_workspace` randomly; Preamble items must pass compilation before PR.
- No agent modifies `src/api.py` endpoint signatures (API contract boundary).
- Paperclip audit logs govern the PR submission pacing.

### Skills to Register

1. **eval-runner** — `python -m evals.*` usage.
2. **git-workflow** — branches, commits, pushing, PR creation.
3. **program-reader** — parsing `PROGRAM.md` baselines and rules.
4. **lean-compiler** — utilizing the isolated compilation tools for harvesting.

### When to Activate

Currently gated on the `LeanInteract` REPL integrations reaching baseline parity, after which the Tree Search Prover mechanics become stable enough for automated tuning.
