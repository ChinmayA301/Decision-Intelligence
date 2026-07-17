# Decision Intelligence

[![CI](https://github.com/ChinmayA301/Decision-Intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/ChinmayA301/Decision-Intelligence/actions/workflows/ci.yml)

Decision Intelligence is a web app for pressure-testing high-stakes business decisions against a curated library of historical decision patterns.

Users describe a decision in plain language. The system frames the decision, retrieves analogous cases from a curated case library (bundled local store by default, Postgres/pgvector optional), runs several strategic lenses, and returns a structured decision brief with reference cases, tensions, and failure modes.

## What It Does

- Structures ambiguous decision text into a typed decision frame.
- Retrieves similar historical decisions from a curated case library.
- Applies four strategy lenses: margin of safety, reversibility, concentration, and optionality.
- Produces a decision brief with cited cases, lens critiques, tension summary, and pre-mortem.
- Stores generated briefs for later retrieval.

This is a research and decision-support tool. It is not legal, financial, or investment advice.

## Stack

- Backend: FastAPI, Python 3.11+
- Frontend: Next.js 14, TypeScript, Tailwind
- Case store: bundled JSON + in-process cosine retrieval by default; Postgres 16 + pgvector optional
- LLM provider: Groq by default, with Anthropic/Ollama support in the provider abstraction
- Embeddings: Jina AI by default, with Voyage/OpenAI support in the provider abstraction

## Local Launch (no database required)

Prerequisites:

- Python 3.11+ and `uv`
- Node.js
- Groq API key (free tier, console.groq.com)
- Jina AI API key (free tier, jina.ai)

Create a local environment file and fill in `GROQ_API_KEY` and `JINA_API_KEY`:

```bash
cp .env.example .env
```

Install dependencies and start the API. With `DATABASE_URL` unset, retrieval is
served from the bundled `data/case_store.json` (the 30 seed cases with
precomputed embeddings) and briefs are stored as local files — no Docker, no
Postgres:

```bash
uv sync --extra dev
uv run uvicorn src.api:app --reload --port 8000
```

Start the web app in a second terminal:

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:3000`, describe a decision, and generate a brief.

The Next.js app proxies `/api/*` requests to `http://localhost:8000` by default.

### Optional: Postgres + pgvector (production path)

Set `DATABASE_URL` in `.env`, then:

```bash
docker compose up -d postgres
uv run python scripts/load_cases.py --force-status reviewed
uv run uvicorn src.api:app --reload --port 8000
```

### Rebuilding the local case store

`data/case_store.json` ships in the repo. Regenerate it after editing seed
cases (requires `JINA_API_KEY`):

```bash
uv run python scripts/build_local_store.py --force-status reviewed
```

## Environment

Required for the default local setup:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
EMBEDDING_PROVIDER=jina
JINA_API_KEY=
JINA_MODEL=jina-embeddings-v3
JINA_TASK=text-matching
# Optional — enables the Postgres/pgvector backend:
# DATABASE_URL=postgresql://sd_user:sd_password@localhost:5432/success_directory
```

Optional provider settings are documented in `.env.example`.

## Repository Layout

```text
src/
  api.py                 FastAPI application
  contracts.py           Typed data contracts
  framer/                Decision framing module
  retriever/             Embedding + retrieval over a CaseStore
  store/                 Case/brief storage backends (local JSON or Postgres)
  critic/                Strategy lens critique module
  synthesizer/           Final brief assembly
  llm/                   LLM provider abstraction
prompts/                 Prompt templates used by the backend
data/                    Seed cases and lens definitions
migrations/              Postgres schema
scripts/                 Data-loading utilities
tests/                   Test suite
web/                     Next.js frontend
docs/                    Technical documentation
```

## Deployment Notes

The frontend can be deployed on Vercel from the `web/` directory.

The backend needs only a Python web host in local-store mode (Render, Railway, Fly.io) — briefs persist to the instance's disk, which is fine for a demo. For durable multi-instance deployments, add a Postgres database with pgvector enabled (Supabase and Neon both work) and set `DATABASE_URL`.

For a split deployment:

- Set `NEXT_PUBLIC_API_URL` in the Vercel frontend project to the deployed API URL.
- Set server-side secrets only on the backend host.
- Do not expose API keys through `NEXT_PUBLIC_*` environment variables.

## Development Checks

```bash
uv run --extra dev ruff check src
uv run --extra dev pytest -q
```
