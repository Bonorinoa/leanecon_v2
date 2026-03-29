# LeanEcon Paperclip Agent Configuration

## Company Structure

Company: LeanEcon
Board: Augusto (Founder)

### Agents to Create

#### 1. LeaneconCEO
- **Role:** Decompose PROGRAM.md research goals into agent tasks
- **Runtime:** Claude Code (plan mode)
- **Budget:** $20/month
- **Heartbeat:** Daily at 09:00
- **Responsibilities:**
  - Read PROGRAM.md and ROADMAP.md
  - Identify the highest-priority autoresearch experiment
  - Create tasks for FormalizerResearcher and ProverResearcher
  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  - Rev  experiment log
  - If not improved: revert, record in experiment log
  - Report results to CEO agent

#### 3. ProverResearcher
- **Role:** Run prover ratchet loop (PROGRAM.md Loop 2)
- **Runtime:** Codex 5.4
- **Budget:** $30/month
- **Heartbeat:** Every 4 hours
- **Responsibilities:**
  - Pick one atomic change to src/prover/prompts.py or src/prover/fast_path.py
  - Run: `python -m evals.prover_only --claim-set agentic_harness`
  - Compare pass@1 to baseline in PROGRAM.md
  - If improved: commit to branch, open PR, record in experiment log
  - If not improved: revert, record in experiment log
  - Report results to CEO agent

#### 4. EvalRunner
- **Role:** Run comprehensive eval suites on demand
- **Runtime:** Codex 5.4
- **Budget:** $10/month
- **Heartbeat:** On task assignment (event-driven)
- **Responsibilities:**
  - Run full eval suite (all tiers, all runners)
  - Generate comparison reports
  - Update docs/PAPER.md result tables
  - Triggered by: merge to main, CEO request, or scheduled weekly

### Org Chart
   ┌─────────┐
   │  Board   │ ← Augusto (approves PRs, sets budgets)
   │(Founder) │
   └────┬─────┘
        │
 ┌──────┴──────┐
 │ LeaneconCEO │ ← Reads PROGRAM.md, creates tasks
 └──┬───┬───┬──┘
    │   │   │
┌─────┴┐ ┌┴────┐ ┌┴─────────┐
│Form. │ │Prov.│ │EvalRunner│
│Rsch. │ │Rsch.│ │          │
└──────┘ └─────┘ └──────────┘

### Governance Rules

- No agent modifies lean_workspace/ (PROGRAM.md preamble gate)
- No agent modifies src/api.py signatures (PROGRAM.md contract gate)
- Every 5 successful experiments → agent opens PR → Board reviews
- Monthly budget review: Board adjusts limits based on ratchet progress
- All tool calls are traced in Paperclip's immutable audit log

### Skills to Register

Each agent should have these skills registered in Paperclip:

1. **eval-runner** — knows how to run `python -m evals.*` commands and parse
   JSON artifacts
2. **git-workflow** — knows how to create branches, commit, push, open PRs
3. **program-reader** — knows how to read PROGRAM.md for baselines, off-limits
   zones, and ratchet rules
4. **experiment-logger** — knows how to write to .cache/autoresearch/*.json

### When to Activate

Do NOT activate Paperclip agents until:
1. [x] Paperclip is installed and dashboard is accessible
2. [ ] Pantograph/LeanInteract integration is complete and benchmarked
3. [ ] At least one manual ratchet cycle has been run successfully
4. [ ] The prover architecture being optimized is the FINAL architecture
   (not the file-compilation architecture we're replacing)

Activating agents on the pre-Pantograph architecture would waste budget
optimizing code paths that are about to be replaced.
