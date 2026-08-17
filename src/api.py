"""FastAPI application — POST /briefs → DecisionBrief.

Storage backend is chosen at startup:
- ``DATABASE_URL`` set   → Postgres + pgvector (production path).
- ``DATABASE_URL`` unset → local JSON case store + file-backed briefs, so the
  full pipeline runs with no external database (demo path).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.contracts import DecisionBrief, FramerClarification
from src.framer.framer import Framer, FramerParseError
from src.llm.client import (
    PROVIDERS,
    LLMClient,
    MissingCredentialError,
    UnknownProviderError,
    build_llm_client,
    get_llm_client,
    server_provider_configured,
)
from src.retriever.retriever import Retriever, create_pool
from src.store.brief_store import BriefStore, LocalBriefStore, MemoryBriefStore, PgBriefStore
from src.store.case_store import LocalCaseStore, PgCaseStore
from src.critic.critic import Critic
from src.synthesizer.synthesizer import Synthesizer

# Nothing in src/ reads the environment at import time — every lookup happens
# inside a function or constructor — so loading .env here, after the imports,
# is early enough for startup and keeps the import block conventional.
load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_CASE_STORE = _PROJECT_ROOT / "data" / "case_store.json"
_LOCAL_BRIEFS_DIR = _PROJECT_ROOT / "data" / "briefs"


def _allowed_origins() -> list[str]:
    """CORS origins from CORS_ALLOW_ORIGINS (comma-separated). Defaults to local
    dev. Set this to the deployed frontend's origin in production — '*' is
    rejected here because callers send API keys on these requests."""
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    origins = [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]
    return origins or ["http://localhost:3000"]


def _build_brief_store() -> tuple[BriefStore, str]:
    """File-backed briefs when the filesystem is writable, in-memory otherwise.

    Serverless platforms mount the deployment read-only, so probe for writability
    rather than assuming it and failing at the end of an expensive request."""
    try:
        _LOCAL_BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
        probe = _LOCAL_BRIEFS_DIR / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
        return LocalBriefStore(_LOCAL_BRIEFS_DIR), "local-file"
    except OSError:
        return MemoryBriefStore(), "memory"


# ─── App state ───────────────────────────────────────────────────────────────

class AppState:
    pool: object | None = None
    store_backend: str = "unset"
    brief_backend: str = "unset"
    llm: LLMClient | None = None
    llm_error: str | None = None
    framer: Framer | None = None
    retriever: Retriever
    briefs: BriefStore
    critic: Critic | None = None
    synthesizer: Synthesizer | None = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("DATABASE_URL"):
        state.pool = await create_pool()
        case_store = PgCaseStore(state.pool)
        state.briefs = PgBriefStore(state.pool)
        state.store_backend = "postgres"
    else:
        if not _LOCAL_CASE_STORE.exists():
            raise RuntimeError(
                f"DATABASE_URL is not set and {_LOCAL_CASE_STORE} is missing. "
                "Run 'python scripts/build_local_store.py' once (needs an embedding "
                "API key) or point DATABASE_URL at Postgres."
            )
        case_store = LocalCaseStore(_LOCAL_CASE_STORE)
        state.briefs, state.brief_backend = _build_brief_store()
        state.store_backend = "local"

    state.retriever = Retriever(store=case_store)

    # A server-side model is optional: a bring-your-own-key deployment boots with
    # no credentials at all and builds a client per request instead. Failing
    # startup here would make that deployment impossible.
    try:
        state.llm = get_llm_client()
        state.framer = Framer(llm=state.llm)
        state.critic = Critic(llm=state.llm)
        state.synthesizer = Synthesizer(critic=state.critic, llm=state.llm)
    except Exception as exc:  # noqa: BLE001 - surfaced via /health, not fatal
        state.llm = None
        state.llm_error = type(exc).__name__

    yield
    if state.pool is not None:
        await state.pool.close()


app = FastAPI(title="Decision Pattern Library API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response schemas ───────────────────────────────────────────────

class BriefRequest(BaseModel):
    user_input: str


class ClarificationResponse(BaseModel):
    type: str = "clarification"
    reason: str
    clarifying_questions: list[str]


@dataclass
class Pipeline:
    """The four stages, bound to one model. Rebuilt per request when the caller
    brings their own key so that credentials never outlive the response."""

    framer: Framer
    critic: Critic
    synthesizer: Synthesizer
    provider: str
    model: str


def _pipeline_for_request(
    provider: str | None,
    model: str | None,
    api_key: str | None,
) -> Pipeline:
    """Caller-supplied credentials win; otherwise use the server's own model.

    The key is never logged and is discarded with the returned object when the
    request ends. Error messages deliberately avoid echoing any credential."""
    if api_key or provider:
        try:
            llm = build_llm_client(provider=provider, model=model, api_key=api_key)
        except UnknownProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except MissingCredentialError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=400, detail="Could not initialise that provider.")
        critic = Critic(llm=llm)
        return Pipeline(
            framer=Framer(llm=llm),
            critic=critic,
            synthesizer=Synthesizer(critic=critic, llm=llm),
            provider=llm.provider,
            model=llm.model,
        )

    if state.llm is None or state.framer is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "This server has no model configured. Supply your own provider and "
                "API key with the request, or set LLM_PROVIDER and its key on the server."
            ),
        )
    return Pipeline(
        framer=state.framer,
        critic=state.critic,
        synthesizer=state.synthesizer,
        provider=state.llm.provider,
        model=state.llm.model,
    )


def _provider_http_error(exc: Exception, provider: str) -> HTTPException:
    """Map an upstream provider failure to a clean client error.

    The upstream message is deliberately never forwarded: provider auth errors
    echo a partially-masked copy of the submitted API key, and relaying that
    would put caller credentials into our response body, logs and browser
    history. Callers get the status and a generic sentence instead.
    """
    status = getattr(exc, "status_code", None)
    if status == 401 or status == 403:
        return HTTPException(
            status_code=401,
            detail=f"{provider} rejected the API key. Check the key and that it has access to the model.",
        )
    if status == 429:
        return HTTPException(
            status_code=429,
            detail=f"{provider} rate limit or quota reached. Wait and retry, or use a different key.",
        )
    if status == 404:
        return HTTPException(
            status_code=400,
            detail=f"{provider} does not recognise that model name.",
        )
    if isinstance(status, int) and 400 <= status < 500:
        return HTTPException(status_code=400, detail=f"{provider} rejected the request.")
    return HTTPException(status_code=502, detail=f"{provider} was unreachable or failed.")


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "store": state.store_backend,
        "brief_store": state.brief_backend,
        "server_model_configured": state.llm is not None,
        "byo_key_required": state.llm is None,
        # Embeddings are server-side and mandatory — callers cannot supply them.
        "embeddings_configured": state.retriever.embedder_ready(),
    }


@app.get("/providers")
async def providers() -> dict:
    """Supported providers, for the settings UI. Advertises no key material —
    only which providers exist and where to get a key for each."""
    return {
        "server_model_configured": server_provider_configured() and state.llm is not None,
        "providers": [
            {
                "id": spec.name,
                "label": spec.label,
                "default_model": spec.default_model,
                "requires_key": spec.requires_key,
                "key_hint": spec.key_hint,
                "signup_url": spec.signup_url,
            }
            for spec in PROVIDERS.values()
        ],
    }


@app.post("/briefs", response_model=DecisionBrief | ClarificationResponse)
async def create_brief(
    req: BriefRequest,
    x_llm_provider: str | None = Header(default=None),
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
):
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="user_input is required")

    pipeline = _pipeline_for_request(x_llm_provider, x_llm_model, x_llm_api_key)

    try:
        # Step 1: Frame
        try:
            framer_output = await pipeline.framer.frame(req.user_input)
        except FramerParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        if isinstance(framer_output, FramerClarification):
            return ClarificationResponse(
                reason=framer_output.reason,
                clarifying_questions=framer_output.clarifying_questions,
            )

        framed = framer_output

        # Step 2: Retrieve (server-side embeddings; no caller credentials involved)
        try:
            refs = await state.retriever.retrieve(framed)
        except RuntimeError as exc:
            # Missing/misconfigured embedding key — an operator problem, not the
            # caller's, so say so plainly rather than returning a generic 500.
            raise HTTPException(status_code=503, detail=str(exc)) from None

        # Step 3: Critique (parallel inside Critic)
        critiques = await pipeline.critic.critique(framed, refs)

        # Step 4: Synthesize
        brief = await pipeline.synthesizer.synthesize(framed, refs, critiques)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - normalised, never echoed verbatim
        raise _provider_http_error(exc, pipeline.provider) from None

    await _store_brief(brief, req.user_input)
    return brief


@app.get("/briefs/{brief_id}", response_model=DecisionBrief)
async def get_brief(brief_id: str):
    brief = await state.briefs.get(brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Brief not found")
    return brief


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _store_brief(brief: DecisionBrief, user_input: str) -> None:
    await state.briefs.save(brief, user_input)
