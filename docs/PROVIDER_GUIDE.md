# Provider Guide

Provider integrations live under `src/drivers` and must implement the protocols
in `src/drivers/base.py`.

## Expectations

- Keep provider-specific transport code inside the driver module.
- Do not execute tools inside the driver; hand every tool call back to the
  proving harness via `on_tool_call`.
- Respect `DriverConfig` values for model selection, temperature, timeouts,
  token budgets, and maximum step counts.
- Keep the V2 API contract unchanged. Providers are an internal runtime choice,
  not an endpoint-level divergence.

## Current Providers

- `mistral`: reference implementation for formalization and proving.
- `gemini`: second implementation proving the driver layer is provider-agnostic.

## Runtime Switching

Set the default provider with `LEANECON_DRIVER`:

```bash
export LEANECON_DRIVER=mistral
export MISTRAL_API_KEY=your_key_here
export MISTRAL_MODEL=labs-leanstral-2603
```

```bash
export LEANECON_DRIVER=gemini
export GEMINI_API_KEY=your_key_here
export GEMINI_MODEL=gemini-3.1-pro-preview
```

The API and formalizer runtime share the same provider resolver, so switching
`LEANECON_DRIVER` changes both the `/api/v2/formalize` and `/api/v2/verify`
provider-backed paths without changing application code.

## Running Evals Against One Provider

Pick the provider in the shell, then run the normal eval commands:

```bash
export LEANECON_DRIVER=gemini
export GEMINI_API_KEY=your_key_here
python3 -m evals.formalizer_only --claim-set tier0_smoke
python3 -m evals.prover_only --claim-set tier0_smoke
python3 -m evals.e2e --claim-set tier0_smoke
```

For Mistral, swap the provider env vars and keep the same commands.

## Adding a New Driver

1. Add any new SDK dependency to `requirements.txt`.
2. Add provider-specific config vars to `src/config.py` and `.env.example`.
3. Create a driver module under `src/drivers/`, using `src/drivers/gemini.py`
   as the reference example.
4. Implement a formalizer driver and register it with
   `@register_formalizer("<name>")`.
5. Implement a prover driver and register it with
   `@register_prover("<name>")`.
6. Map the provider SDK onto `DriverConfig` rather than leaking provider
   settings into the harness or API layer.
7. Import the new module in `src/drivers/registry.py` so the decorators run at
   import time.
8. Extend `src/drivers/provider_config.py` so `LEANECON_DRIVER=<name>` selects
   the correct model and API key.
9. Add driver tests that mock the SDK and verify config mapping, tool-call
   execution, error wrapping, and registry exposure.
10. Run `ruff check src tests evals` and the relevant `pytest` suites.

## Gemini vs Mistral Tool Calls

- Mistral uses chat messages plus `tool_calls` and returns tool arguments as a
  JSON string or dict on `message.tool_calls[*].function.arguments`.
- Gemini uses `generate_content` with `types.Tool` declarations and returns
  function calls in response parts via `part.function_call`.
- Mistral tool results are appended as chat messages with role `tool`.
- Gemini tool results are appended as `types.Content(role="tool", ...)` using
  `types.Part.from_function_response(...)`.

Both drivers normalize these differences into the same LeanEcon event stream:
`tool_call`, `tool_result`, `assistant`, `done`, and `error`.

## Scope Note

The provider abstraction currently covers the formalize and verify paths.
`/api/v2/explain` still uses the Mistral-specific implementation in
`src/explainer/explainer.py` and is not yet routed through `src/drivers`.
