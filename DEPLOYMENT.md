# Deployment

Two pieces deploy separately: the FastAPI backend and the Next.js frontend. Both
can live on Vercel, as two projects pointed at the same repository with different
root directories.

```
repo root  →  Vercel project "decision-intelligence-api"  (Python functions)
web/       →  Vercel project "decision-intelligence-web"  (Next.js)
```

## What the server needs

| Requirement | Needed? | Why |
|---|---|---|
| Embedding key (`JINA_API_KEY`) | **Yes** | Every brief embeds the user's decision text to retrieve cases. This is one small call per brief and cannot be pushed to the visitor. |
| LLM key (`GROQ_API_KEY` etc.) | Optional | If unset, the app runs bring-your-own-key: visitors supply their own provider and key and the model calls run on their quota, not yours. |
| Database | No | Retrieval reads the bundled `data/case_store.json`. Set `DATABASE_URL` only if you want Postgres + pgvector. |

Leaving the LLM key unset is the recommended setup for a public demo — it is the
only configuration where traffic cannot exhaust your own quota.

## 1. Backend

Create a Vercel project with **root directory = repository root**. `vercel.json`
routes every path to `api/index.py`, which serves the FastAPI app.

Environment variables:

```
JINA_API_KEY=...                     # required
EMBEDDING_PROVIDER=jina              # default
CORS_ALLOW_ORIGINS=https://your-frontend.vercel.app
# Optional — omit for bring-your-own-key only:
# LLM_PROVIDER=groq
# GROQ_API_KEY=...
```

`CORS_ALLOW_ORIGINS` is comma-separated. `*` is deliberately ignored: visitors
send API keys on these requests, so the allowed origin must be explicit.

Notes on the serverless environment:

- **Briefs are stored in memory.** The deployment filesystem is read-only, so the
  app detects this at startup and falls back to an in-memory store (capped at 200
  briefs). Briefs do not survive a restart and are not shared across instances, so
  a `/briefs/{id}` share link may 404 if it lands on a different instance. Set
  `DATABASE_URL` if you need durable, shareable links.
- **`maxDuration` is 60s** in `vercel.json`. A brief normally completes in about
  7 seconds; the headroom covers provider rate-limit retries. Free Vercel plans
  cap function duration lower than this — check your plan if briefs time out.
- `asyncpg`, `pgvector` and `voyageai` are excluded from `requirements.txt` to keep
  the bundle small. Add them back if you enable Postgres or Voyage embeddings.

## 2. Frontend

Create a second Vercel project with **root directory = `web`**.

```
NEXT_PUBLIC_API_URL=https://your-api.vercel.app
```

`web/next.config.js` proxies `/api/*` to that URL, so the browser talks to the
frontend's own origin and the backend origin appears only in configuration.

Deploy the backend first so you have its URL, then set `CORS_ALLOW_ORIGINS` on the
backend to the frontend URL once both exist.

## Alternative: single container

The backend runs anywhere that can run Python. There is no database or writable
disk requirement, so a plain container works:

```bash
pip install -r requirements.txt
uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}
```

Render, Railway and Fly.io all take this directly. On a host with a writable
disk, briefs persist to `data/briefs/` automatically instead of memory.

## Bring your own key: how it works

1. The visitor opens **Use your own model**, picks a provider, and pastes a key.
2. The key is stored in that browser's `localStorage` and sent with the brief
   request as `X-LLM-Api-Key`, alongside `X-LLM-Provider` and optional `X-LLM-Model`.
3. The server builds an LLM client for that request only. The key is never
   written to disk, never logged, and never included in the generated brief.
4. If the provider rejects the key, the caller gets a clean `401` — the upstream
   message is not relayed, because provider auth errors echo a partially-masked
   copy of the submitted key.

Base URLs come from a fixed provider registry in `src/llm/client.py` and are never
taken from caller input. Accepting a caller-supplied URL would let an attacker
point the request at a host they control and harvest the key.

Supported providers: Groq, Anthropic, OpenAI, OpenRouter, and Ollama (local, no
key). `GET /providers` returns the list the settings UI renders.

### Trust boundary

A visitor's key passes through your server in memory to reach their provider.
That is unavoidable for a server-side pipeline, and the UI states it plainly.
Anyone deploying this publicly should keep it in mind: you are asking visitors to
trust your deployment with a credential. If that is not acceptable for your
audience, run the backend with your own key and rate-limit it instead.
