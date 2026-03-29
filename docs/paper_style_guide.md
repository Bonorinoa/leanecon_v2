# Paper Maintenance Guide for Agents

## Purpose
`docs/PAPER.md` is a living academic paper. Update it after each benchmark run.

## Rules
1. Never invent numbers. Always read from `.cache/evals/*.json` artifacts.
2. Use `[PLACEHOLDER: description]` for missing data. Never leave a bare number without verifying it against an artifact file.
3. Keep the abstract under 200 words.
4. Tables must have source artifact paths in a comment above them.
5. The LaTeX file (`docs/paper/main.tex`) must stay in sync with `PAPER.md`.
6. References use author-year format via `natbib`.
7. Figures go in `docs/paper/figures/` as PDF or PNG.
8. When updating results sections, also update the abstract if the key numbers changed.
9. Any change to results text or tables in `docs/PAPER.md` must be mirrored in `docs/paper/main.tex` in the same edit.

## How to Update After a Benchmark Run
1. Read the JSON artifacts in `.cache/evals/`
2. Update the relevant table in Section 5
3. Update the abstract if pass@1 changed significantly
4. Update `docs/paper/main.tex` to match
5. Commit with message: `"docs: update paper results from [eval name] run"`
