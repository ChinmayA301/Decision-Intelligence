# Architecture

## Stack
- **Backend:** FastAPI (Python 3.11+)
- **Database:** Postgres 16 with `pgvector`
- **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind
- **LLM:** Provider abstraction with Groq as the default cloud option and Anthropic/Ollama support
- **Embeddings:** Provider abstraction with Jina AI as the default cloud option and Voyage/OpenAI support
- **Hosting (MVP):** Single Fly.io app + managed Postgres. No Kubernetes. No microservices.

## Module-by-module

### Framer
**Input:** raw user text (a decision they're facing, free-form 1–3 paragraphs).
**Output:** `FramedDecision` (typed JSON).
**Implementation:** single LLM call with strict JSON schema. Retries on schema-validation failure (max 2). If still failing, returns an error to the UI asking the user to rephrase.

Key prompt design decisions:
- Forces the user's decision into a binary or small-discrete-set choice. If the user describes a strategic muddle with no clear options, the framer asks clarifying questions back rather than fabricating options.
- Distinguishes `reversibility: one_way | two_way` explicitly — this routes to which lens gets emphasis.
- Records `key_uncertainties` separately — these become retrieval queries.

### Retriever
**Input:** `FramedDecision`.
**Output:** `ReferenceClass` containing 5–10 cases with similarity scores.
**Implementation:**
1. Embed `FramedDecision.context_summary + .choice_being_made`
2. pgvector cosine search top-30
3. Rerank: hard filter on `domain` match (with a fallback to "any domain" if <4 hits), boost matching `decision_type`, penalize `era_dependence: high` unless user's context shares the era markers
4. Truncate to 10
5. Compute base-rate stats over the retrieved set: % success, % mixed, % failure

If fewer than 4 cases match after filters, the response includes a `weak_reference_class: true` flag, which the UI surfaces prominently.

### Critic
**Input:** `FramedDecision` + `ReferenceClass`.
**Output:** `list[LensCritique]` — one per lens, run in parallel.
**Implementation:** 4 parallel LLM calls, each with a different lens prompt template. Each lens has access to the framed decision and the reference class.

Each `LensCritique` returns:
- `verdict`: `endorses | endorses_with_caveats | rejects | abstains`
- `reasoning`: 3–5 sentences
- `key_questions`: 2–3 questions the user should answer before proceeding
- `most_relevant_case_ids`: which retrieved cases this lens leans on

The `abstains` verdict is important — a lens should be allowed to say "this decision isn't in my domain of relevance."

### Synthesizer
**Input:** all of the above.
**Output:** `DecisionBrief` (the final user-facing artifact).
**Implementation:** mostly assembly, not generation. One short LLM call to write a "tension summary" — a 2-sentence note on where the lenses disagreed.

Calibration checks the synthesizer enforces before returning:
- ≥3 cases cited across all lenses
- At least one lens references a `failure` outcome from the reference class
- Tension between lenses logged as a feature, not smoothed over

If checks fail, the synthesizer rejects its own output and re-runs the critics with an injected note ("the previous run produced converged critiques; produce more divergent reasoning"). Max 1 retry.

## Data flow diagram

```
                                    ┌──────────────────┐
                                    │  Pattern Library │
                                    │  (Postgres+vec)  │
                                    └────────┬─────────┘
                                             │
   user text                                 │ retrieve
       │                                     │
       ▼                                     ▼
  ┌─────────┐    FramedDecision     ┌─────────────────┐  ReferenceClass
  │ Framer  │ ──────────────────▶   │   Retriever     │ ─────────────┐
  └─────────┘                       └─────────────────┘              │
                                                                     │
                                                                     ▼
                                              ┌──────────────────────────────┐
                                              │   Critic (×4 lenses, parallel)│
                                              └──────────────┬───────────────┘
                                                             │ list[LensCritique]
                                                             ▼
                                                    ┌─────────────────┐
                                                    │   Synthesizer   │
                                                    └────────┬────────┘
                                                             │
                                                             ▼ DecisionBrief
                                                          (to UI)
```

## What's deliberately missing (and why)

- **No vector DB beyond pgvector.** At 150 cases, a $40/mo managed Postgres is sufficient. Pinecone/Weaviate adds ops surface for no MVP benefit.
- **No agent framework (LangChain/LangGraph/etc.).** The reasoning loop has 4 steps. Plain Python and httpx is clearer than any framework.
- **No fine-tuning.** Prompts + retrieval are sufficient. Fine-tuning is a Phase 4+ optimization.
- **No streaming responses.** Users expect to wait 15–30 seconds for a serious analysis. Streaming creates a fake "AI is thinking" UX that we explicitly want to avoid — we want users to feel they got a researched brief, not a chat.

## Performance budget
- Total response time: 20–40 seconds (acceptable, this is not a chat product)
- Framer: ~3s
- Retriever: ~1s (pgvector is fast)
- Critic (parallel): ~15s (gated by slowest lens)
- Synthesizer: ~5s
- Cost per brief: target <$0.30 in API spend at MVP.

## Failure modes the system explicitly handles

| Failure | Detection | Response |
|---|---|---|
| Framer can't structure decision | JSON validation fails twice | Return clarifying questions to user |
| Retriever finds <4 matching cases | Count check | Set `weak_reference_class` flag, render banner in UI |
| All 4 lenses converge | Pairwise embedding distance | Re-run with divergence injection prompt |
| LLM hallucinates a case not in library | Synthesizer cross-checks `most_relevant_case_ids` against DB | Strip uncited claims |
| Whole pipeline fails | API gateway timeout 60s | Return graceful error, log for review |
