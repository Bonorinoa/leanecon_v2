# Provider Guide

Provider integrations belong under `src/drivers` and must implement the
protocols in `src/drivers/base.py`.

## Expectations

- Keep provider-specific transport code inside the driver.
- Do not execute tools inside the driver; hand tool calls back to the harness.
- Respect configured timeouts, token budgets, and maximum step counts.

## Phase 2A

The Mistral adapter is a scaffold only. Real proving and formalization calls are
planned for later phases after the API surface and job model stabilize.
