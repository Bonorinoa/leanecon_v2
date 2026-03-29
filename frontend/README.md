# LeanEcon v2 Demo

Interactive frontend for the LeanEcon formal verification API.

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The app connects to the API at
`http://localhost:8000` by default.

Set `VITE_API_URL` in `.env` to point to a deployed API instance.

## Features

- Three-panel layout: input -> theorem review -> verification progress
- Real-time SSE progress timeline during proving
- Full pipeline: search -> formalize -> review -> verify -> explain
- Editable theorem review (human-in-the-loop)
- History of recent verifications
- Dark theme with a professional research-tool aesthetic

## Architecture

The frontend is a thin client. All intelligence lives in the API.
The frontend presents the three-layer trust model clearly:

1. Show the stochastic layer as in-progress work.
2. Enable the human layer through theorem review and editing.
3. Celebrate the deterministic layer when the Lean kernel accepts a proof.
