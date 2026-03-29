# LeanEcon Paperclip Local Setup

This workspace ships a Paperclip company scaffold for four operational agents:
CEO, FormalizerResearcher, ProverResearcher, and EvalRunner.

The config lives under [`.paperclip/`](../.paperclip/) and is wired for a local
Ollama endpoint so the autoresearch loops do not consume hosted API credits.

## 1. Start Ollama

Install Ollama if needed, then start the local server:

```bash
ollama serve
```

Pull the default model used by the config:

```bash
ollama pull mistral
```

Optional fallback model:

```bash
ollama pull llama3
```

If your Paperclip build expects an OpenAI-compatible base URL instead of the
native Ollama endpoint, point it at `http://127.0.0.1:11434/v1`. The checked-in
config currently uses `http://127.0.0.1:11434`.

## 2. Load the company config

The root manifest is [`.paperclip/paperclip.yaml`](../.paperclip/paperclip.yaml).
It references the four agent definitions in [`.paperclip/agents/`](../.paperclip/agents/).

Launch Paperclip from the repository root and point it at that manifest using
the config flag supported by your installed Paperclip CLI. The exact command
varies across Paperclip builds, so this repo keeps the manifest explicit rather
than assuming one verb.

## 3. Recommended activation order

1. Confirm the LeanInteract REPL baseline is in place.
2. Start Ollama and verify `mistral` responds on the local endpoint.
3. Load the Paperclip company config from `.paperclip/paperclip.yaml`.
4. Let CEO orchestrate the first ratchet loop.
5. Run EvalRunner after each candidate prompt or heuristic change.

## 4. Benchmark commands

These are the commands the agents are configured to use:

```bash
python -m evals.formalizer_only --claim-set tier0_smoke
python -m evals.formalizer_only --claim-set tier1_core
python -m evals.prover_only --claim-set tier0_smoke
python -m evals.prover_only --claim-set agentic_harness
python -m evals.e2e --claim-set tier0_smoke
python -m evals.e2e --claim-set agentic_harness
python -m evals.report
```

## 5. Guardrails

- Do not let any agent edit the off-limits zones from [PROGRAM.md](../PROGRAM.md).
- Any Lean preamble addition under `lean_workspace/LeanEcon/Preamble/` still
  requires human approval.
- EvalRunner owns benchmark execution and summary updates.
- CEO should delegate, not directly rewrite prover or formalizer logic.