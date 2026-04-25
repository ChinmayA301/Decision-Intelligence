# HANDOFF.md — paste this into Claude Code

You are picking up a project called **Success Directory**. The vision and design are already specified. Your job is implementation, not invention.

## Step 0 — orient

Read these in order, fully, before writing any code:
1. `/README.md` — the constitution
2. `/docs/critique-of-original.md` — why we are NOT doing IRL/CATE/Bayesian-fusion. Critical context for resisting scope creep.
3. `/docs/architecture.md` — module-by-module spec
4. `/docs/data-model.md` — schemas and vocabulary
5. `/docs/eval-plan.md` — how we know the work is good
6. `/src/contracts.py` — the typed contracts. **Do not change without discussion.**
7. `/prompts/framer.md` and `/prompts/lens_margin_of_safety.md` — prompt style examples

## Step 1 — set up the repo

- Initialize git, `.gitignore`, `pyproject.toml` with: fastapi, pydantic, asyncpg, anthropic, voyageai (or openai), pgvector
- Frontend: `pnpm create next-app` in `/web/` — TypeScript, Tailwind, App Router
- Set up Postgres locally via docker-compose with pgvector image
- Run migrations from the DDL in `/docs/data-model.md`

Do not introduce: LangChain, LangGraph, CrewAI, or any agent framework. Do not introduce Pinecone/Weaviate. Do not introduce a microservice split. The product is small; keep the code small.

## Step 2 — implement in this order

Build vertically, not horizontally. Get one thin slice end-to-end before going wide.

1. **Framer module first.** It's the smallest, fully self-contained, and unblocks every test.
   - Implement `src/framer/framer.py` against the `FramerProtocol`
   - Use Anthropic Claude Sonnet
   - Use response-schema enforcement (Anthropic's `response_format` or strict JSON parsing with retry)
   - Write `tests/test_framer.py` against the 4 test decisions in `evals/test_decisions.yaml`
   - Stop here, get review

2. **Seed cases + Retriever.**
   - Write 30 cases in `data/seed_cases/*.yaml` following `netflix-qwikster-2011.yaml` as template
     - Every case needs ≥2 sources. No exceptions. If you can't find sources, drop the case.
     - Distribute across 6 domains (5 each)
   - Write `scripts/load_cases.py` to ingest YAML → Postgres, computing embeddings on `context_summary + choice_being_made`
   - Implement `src/retriever/retriever.py`
   - Test: every test decision retrieves ≥4 cases, returns correct base_rate math

3. **Critic.**
   - Write the other 3 lens prompts using `lens_margin_of_safety.md` as template
   - Implement `src/critic/critic.py` with parallel async calls (4 lenses simultaneously)
   - Test: divergence check P4 from eval plan

4. **Synthesizer.**
   - Implement `src/synthesizer/synthesizer.py`
   - Implement calibration checks
   - Implement the divergence-retry loop (max 1 retry)

5. **API + minimal UI.**
   - FastAPI route: `POST /briefs` → returns `DecisionBrief`
   - Next.js page with composer textarea + brief renderer
   - No auth in MVP; use a UUID for share links

## Step 3 — run the evals

`pytest evals/process_evals.py` must pass before claiming Phase 1 done.

Then implement `evals/adversarial.py` and run it. Document what fails.

## Constraints / things you must not do

- Do NOT relax the typed contracts in `src/contracts.py` to make a failing module pass. Fix the module.
- Do NOT add a "decision score" or any number that pretends to be a calibrated probability of success. We do not output that. Read `/docs/critique-of-original.md` if tempted.
- Do NOT generate first-person quotes from real people. Lenses are reasoning templates, not impersonations.
- Do NOT make Framer fall back to "framing anyway" when it should clarify. Better to ask than to invent.
- Do NOT publish a case with `review_status: draft` to retrieval. Filter on `reviewed`.
- Do NOT implement IRL, MaxEnt anything, DML, CATE, or any of the math from the original brief. If a stakeholder asks for it, point them at `/docs/critique-of-original.md`.

## What done looks like for Phase 1

- 30 reviewed seed cases in DB
- API endpoint that returns a valid `DecisionBrief` for any of the 20 test decisions
- All Layer-1 process evals (P1–P9) passing at the targets in `eval-plan.md`
- A Loom-style demo or README screenshot of one full brief end-to-end

## When you're stuck

Open issues against the `success-directory` repo with the prefix `[design-q]`. Don't silently re-interpret the spec.
