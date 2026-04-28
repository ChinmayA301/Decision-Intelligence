# Decision Intelligence

Decision Intelligence is a web app for pressure-testing high-stakes business decisions against a curated library of historical decision patterns.

Users describe a decision in plain language. The system frames the decision, retrieves analogous cases from a Postgres/pgvector library, runs several strategic lenses, and returns a structured decision brief with reference cases, tensions, and failure modes.

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
- Database: Postgres 16 with pgvector
- LLM provider: Groq by default, with Anthropic/Ollama support in the provider abstraction
- Embeddings: Jina AI by default, with Voyage/OpenAI support in the provider abstraction

## Local Launch

Prerequisites:

- Docker
- Python 3.11+
- `uv`
- Node.js
- Groq API key
- Jina AI API key

Create a local environment file:

```bash
cp .env.example .env
```

Fill in `GROQ_API_KEY` and `JINA_API_KEY` in `.env`.

Start Postgres with pgvector:

```bash
docker compose up -d postgres
```

Install Python dependencies and load seed cases:

```bash
uv sync --extra dev
uv run python scripts/load_cases.py --force-status reviewed
```

Start the API:

```bash
uv run uvicorn src.api:app --reload --port 8000
```

Start the web app in a second terminal:

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:3000`.

The Next.js app proxies `/api/*` requests to `http://localhost:8000` by default.

## Environment

Required for the default local setup:

```env
DATABASE_URL=postgresql://sd_user:sd_password@localhost:5432/success_directory
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
EMBEDDING_PROVIDER=jina
JINA_API_KEY=
JINA_MODEL=jina-embeddings-v3
JINA_TASK=text-matching
```

Optional provider settings are documented in `.env.example`.

## Repository Layout

```text
src/
  api.py                 FastAPI application
  contracts.py           Typed data contracts
  framer/                Decision framing module
  retriever/             Embedding and pgvector retrieval
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

The backend needs a Python web host and a Postgres database with pgvector enabled. Render, Railway, Fly.io, Supabase, and Neon are reasonable options depending on how you want to split API hosting and database hosting.

For a split deployment:

- Set `NEXT_PUBLIC_API_URL` in the Vercel frontend project to the deployed API URL.
- Set server-side secrets only on the backend host.
- Do not expose API keys through `NEXT_PUBLIC_*` environment variables.

## Development Checks

```bash
uv run --extra dev ruff check src
uv run --extra dev pytest -q
```
