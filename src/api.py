"""FastAPI application — POST /briefs → DecisionBrief.

Storage backend is chosen at startup:
- ``DATABASE_URL`` set   → Postgres + pgvector (production path).
- ``DATABASE_URL`` unset → local JSON case store + file-backed briefs, so the
  full pipeline runs with no external database (demo path).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.contracts import DecisionBrief, FramerClarification
from src.framer.framer import Framer, FramerParseError
from src.llm.client import LLMClient, get_llm_client
from src.retriever.retriever import Retriever, create_pool
from src.store.brief_store import BriefStore, LocalBriefStore, PgBriefStore
from src.store.case_store import LocalCaseStore, PgCaseStore
from src.critic.critic import Critic
from src.synthesizer.synthesizer import Synthesizer

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_CASE_STORE = _PROJECT_ROOT / "data" / "case_store.json"
_LOCAL_BRIEFS_DIR = _PROJECT_ROOT / "data" / "briefs"


# ─── App state ───────────────────────────────────────────────────────────────

class AppState:
    pool: object | None = None
    store_backend: str = "unset"
    llm: LLMClient
    framer: Framer
    retriever: Retriever
    briefs: BriefStore
    critic: Critic
    synthesizer: Synthesizer


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
        state.briefs = LocalBriefStore(_LOCAL_BRIEFS_DIR)
        state.store_backend = "local"

    state.llm = get_llm_client()
    state.framer = Framer(llm=state.llm)
    state.retriever = Retriever(store=case_store)
    state.critic = Critic(llm=state.llm)
    state.synthesizer = Synthesizer(critic=state.critic, llm=state.llm)
    yield
    if state.pool is not None:
        await state.pool.close()


app = FastAPI(title="Decision Pattern Library API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "store": state.store_backend}


@app.post("/briefs", response_model=DecisionBrief | ClarificationResponse)
async def create_brief(req: BriefRequest):
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="user_input is required")

    # Step 1: Frame
    try:
        framer_output = await state.framer.frame(req.user_input)
    except FramerParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if isinstance(framer_output, FramerClarification):
        return ClarificationResponse(
            reason=framer_output.reason,
            clarifying_questions=framer_output.clarifying_questions,
        )

    framed = framer_output

    # Step 2: Retrieve
    refs = await state.retriever.retrieve(framed)

    # Step 3: Critique (parallel inside Critic)
    critiques = await state.critic.critique(framed, refs)

    # Step 4: Synthesize
    brief = await state.synthesizer.synthesize(framed, refs, critiques)

    # Persist brief to DB
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
