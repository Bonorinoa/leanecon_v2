# LeanEcon v2

LeanEcon v2 is a provider-agnostic formal verification API for mathematical
economics claims. It turns natural-language or Lean inputs into machine-checkable
theorems, routes proof generation through an LLM-driven prover harness, and uses
the Lean 4 kernel as the deterministic source of truth.

## Quick Start

```bash
git clone https://github.com/Bonorinoa/leanecon_v2.git
cd leanecon_v2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.api:app --reload
```

The API contract lives in [docs/API_CONTRACT.md](docs/API_CONTRACT.md) and the
system overview lives in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

`alpha` — scaffold complete, core implementation in progress.

## Railway

LeanEcon ships with a `railway.toml` and Docker-based deploy path. Railway can
probe `/health` after boot, and the image prebuilds the Lean workspace so
`/api/v2/compile` is ready without a first-request build.

`MISTRAL_API_KEY` is optional for deployment. When it is unset, `/health`,
`/api/v2/search`, and `/api/v2/compile` remain live, while provider-backed
formalization/proving falls back gracefully instead of crashing the service.

## License

Apache-2.0. See [LICENSE](LICENSE).
