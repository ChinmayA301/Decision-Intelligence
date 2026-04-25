"""FastAPI application — POST /briefs → DecisionBrief."""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import anthropic
import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.contracts import DecisionBrief, FramerClarification
from src.framer.framer import Framer, FramerParseError
from src.retriever.retriever import Retriever, create_pool
from src.critic.critic import Critic
from src.synthesizer.synthesizer import Synthesizer


# ─── App state ───────────────────────────────────────────────────────────────

class AppState:
    pool: asyncpg.Pool
    client: anthropic.AsyncAnthropic
    framer: Framer
    retriever: Retriever
    critic: Critic
    synthesizer: Synthesizer


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.pool = await create_pool()
    state.client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    state.framer = Framer(client=state.client)
    state.retriever = Retriever(pool=state.pool)
    state.critic = Critic(client=state.client)
    state.synthesizer = Synthesizer(critic=state.critic, client=state.client)
    yield
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
    return {"status": "ok"}


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
    async with state.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT final_brief FROM briefs WHERE brief_id = $1",
            brief_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Brief not found")
    return DecisionBrief.model_validate_json(row["final_brief"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _store_brief(brief: DecisionBrief, user_input: str) -> None:
    async with state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO briefs (brief_id, user_input, framed_decision, reference_class,
                                lens_critiques, final_brief)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (brief_id) DO NOTHING
            """,
            brief.brief_id,
            user_input,
            brief.framed_decision.model_dump_json(),
            brief.reference_class.model_dump_json(),
            "[" + ",".join(c.model_dump_json() for c in brief.lens_critiques) + "]",
            brief.model_dump_json(),
        )
