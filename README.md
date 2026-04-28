# Success Directory — Decision Intelligence Engine

This repo defines the scope, architecture, data model, and MVP build plan for a Decision Intelligence (DI) tool that helps users make high-stakes ambiguous decisions by surfacing relevant historical decision patterns and grounding recommendations in causal evidence — not vibes.

---

## Local launch

Prerequisites: Docker, Python 3.11+, `uv`, Node.js, and API keys for Groq and Jina AI.

1. Create your local environment file:

```bash
cp .env.example .env
```

Then fill in `GROQ_API_KEY` and `JINA_API_KEY`.

2. Start Postgres with pgvector:

```bash
docker compose up -d postgres
```

3. Install/sync Python dependencies and load the seed cases:

```bash
uv sync --extra dev
uv run python scripts/load_cases.py --force-status reviewed
```

4. Start the FastAPI backend:

```bash
uv run uvicorn src.api:app --reload --port 8000
```

5. Start the web app in a second terminal:

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:3000`. The web app proxies `/api/*` requests to `http://localhost:8000` by default.

---

## 0. Read this first — what changed from the original KT brief

The original brief was philosophically interesting but technically over-promised. Before any code is written, the following corrections are baked into this plan:

| Original framing | Problem | Replacement |
|---|---|---|
| "Recover the reward function of Jobs / Buffett / Iger via MaxEnt IRL" | IRL needs dense state-action trajectories. We have anecdotes. The math will run on garbage and produce garbage. | **Heuristic Extraction via structured LLM annotation** of curated case studies → a typed *Decision Pattern Library*. IRL is parked as a v3 research bet, not v1. |
| "CATE / DML over historical decisions" | Strategic decisions are largely n=1; no treatment/control overlap. DML on this data is pseudoscience. | **Reference-class forecasting** (Kahneman/Lovallo): retrieve a reference class of analogous decisions, report base rates, and let the user adjust. Causal language is reserved for sub-decisions where data actually exists (pricing, hiring, marketing spend). |
| "Bayesian fusion of Causal × Instinct posteriors" | The equation in the brief assumes independence and well-calibrated posteriors that don't exist. | **Two-panel output**: (a) reference-class base rate with confidence interval, (b) heuristic critique from N expert patterns. No fake unified score. |
| "Success Directory" | Vague name — directory of what? | **Decision Pattern Library** (the asset) + **Decision Brief** (the output artifact). |
| Section 6: "Build vector DB of decision triplets" | That's a 2-year research program. | MVP uses ~150 hand-curated cases. Scale only after we prove the loop works. |

**Core thesis preserved:** Users facing ambiguous high-stakes decisions benefit from (1) being forced to articulate their decision cleanly, (2) seeing a reference class of analogous past decisions with outcomes, (3) being challenged by 2–4 distinct expert heuristic lenses. That is the product.

---

## 1. Product definition

### 1.1 What it is
A web tool where a user describes a decision they're facing. The system returns a **Decision Brief** containing:

1. **Decision framing** — the system's structured re-statement of the decision (what's actually being chosen, what's the counterfactual, what's the time horizon).
2. **Reference class** — 5–10 historical decisions with similar structure, their outcomes, and the empirical base rate.
3. **Expert lenses** — 2–4 heuristic critiques of the decision from named perspectives (e.g., "Buffett-style margin-of-safety lens", "Bezos-style reversibility lens"). Each lens is a *reasoning template applied to your specific decision*, not a celebrity impersonation.
4. **Pre-mortem** — likely failure modes drawn from reference-class failures.
5. **Risk-appetite slider** — same decision re-scored at conservative / balanced / aggressive postures.

### 1.2 What it is NOT
- It is not an oracle. It does not output "do X" with a probability score that pretends to be calibrated.
- It is not a celebrity simulator. We do not generate first-person quotes from real people.
- It is not a causal inference engine for strategic decisions. We are honest about the n=1 nature of most strategic choices.

### 1.3 Job to be done
> "I'm facing a decision that matters, my team is split, and I want to pressure-test my thinking against patterns from people who've faced structurally similar choices — without wasting six hours googling case studies."

### 1.4 Target user (v1)
Founders, GMs, and senior PMs at companies with $1M–$50M ARR facing decisions in: pricing changes, M&A, market entry, key hires, product sunsets, capital allocation. Narrow on purpose.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         WEB CLIENT                              │
│  Decision Composer → Brief Viewer → Expert Lens Toggles         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                  ┌────────────▼────────────┐
                  │      API GATEWAY        │
                  │     (FastAPI / TS)      │
                  └────────────┬────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼────────┐   ┌─────────▼─────────┐   ┌────────▼────────┐
│   FRAMER       │   │   RETRIEVER       │   │   CRITIC        │
│ Structures the │   │ Finds reference   │   │ Applies expert  │
│ raw decision   │   │ class via vector  │   │ lenses + pre-   │
│ into typed     │   │ search over       │   │ mortem to       │
│ schema         │   │ Pattern Library   │   │ framed decision │
└───────┬────────┘   └─────────┬─────────┘   └────────┬────────┘
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                  ┌────────────▼────────────┐
                  │     SYNTHESIZER         │
                  │  Assembles Decision     │
                  │  Brief, runs            │
                  │  calibration checks     │
                  └────────────┬────────────┘
                               │
                  ┌────────────▼────────────┐
                  │    PATTERN LIBRARY      │
                  │  (Postgres + pgvector)  │
                  │  Cases, Lenses, Outcomes│
                  └─────────────────────────┘
```

**Why this shape:** Each box is a small LLM-orchestrated module with a typed input/output contract. They can be tested, swapped, and benchmarked independently. No monolithic "decision model."

---

## 3. The data asset: Decision Pattern Library

This is the moat. Not the math.

### 3.1 Schema (the unit of value)

Every `Case` is one historical decision. Hand-curated, sourced from books, HBR cases, court filings, earnings calls, biographies. Each case has:

```yaml
case_id: str
title: str                    # "Netflix splits DVD and streaming (Qwikster), 2011"
decision_maker: str            # "Reed Hastings"
year: int
domain: enum                   # pricing | m_and_a | market_entry | hiring | ...
decision_type: enum            # reversible | one_way_door | sequential
context_summary: str           # 2-3 paragraphs, neutral
options_considered: list[str]
option_taken: str
stated_rationale: str          # what they said publicly at the time
inferred_heuristics: list[str] # tagged from a closed vocabulary
constraints_at_time: list[str] # capital, talent, regulatory, competitive
outcome_12mo: str
outcome_36mo: str
outcome_label: enum            # success | mixed | failure | too_early
counterfactual_signal: str     # what comparable peers did instead, if known
sources: list[Citation]        # required, ≥2, primary preferred
embedding: vector(1536)        # over context_summary + decision framing
review_status: enum            # draft | reviewed | published
```

### 3.2 Closed-vocabulary heuristics
A controlled tag set (~40 tags) for `inferred_heuristics`. Examples:
- `margin_of_safety`, `reversibility_first`, `concentration_bet`, `optionality_preserve`,
  `speed_over_consensus`, `consensus_required`, `cash_runway_priority`, `talent_density_bet`,
  `narrative_control`, `regulatory_arbitrage`, `vertical_integration`, `platform_neutrality`...

This vocabulary is the connective tissue between cases and the Expert Lenses. Lenses are defined as *weighted combinations* of these tags, not as personalities.

### 3.3 v1 corpus target
**150 cases.** Distributed across the 6 target domains. Curated with human review, every case reviewed by a human before publication. Estimated effort: 2–3 weeks for one senior researcher.

---

## 4. Expert Lenses (replacement for "Instinct Engine")

A `Lens` is a reasoning template, not a person. Each lens is defined by:

```yaml
lens_id: str
display_name: str                   # "Margin-of-Safety Lens"
inspired_by: list[str]              # ["Buffett", "Graham"] — for color, not authority
priority_heuristics: list[tag]      # ordered, weighted
disqualifying_heuristics: list[tag] # things this lens rejects
prompt_template: str                # how the lens critiques a Framed Decision
example_critiques: list[str]        # gold-standard examples for few-shot
```

**v1 lens slate (4 total, deliberately covering the strategy space):**
1. Margin-of-Safety Lens (conservative capital allocation)
2. Reversibility Lens (Bezos-style one-way vs two-way doors)
3. Concentration Lens (high-conviction big-bet posture)
4. Optionality Lens (preserve future moves, defer commitment)

These four span a 2x2: (concentrate vs diversify) x (commit vs defer). The user always sees critiques from all four; the UI highlights the two most divergent ones for the specific decision.

---

## 5. The reasoning loop (per-request flow)

```
USER INPUT
  ↓
[FRAMER]  LLM call with strict JSON schema → FramedDecision
          fields: choice_being_made, alternatives, time_horizon,
                  reversibility, key_uncertainties, constraints
  ↓
[RETRIEVER]  embed(FramedDecision) → top_k cases from pgvector
             rerank by domain match + decision_type match
             → ReferenceClass(cases=[...], base_rate={...})
  ↓
[CRITIC × 4 lenses in parallel]  for each lens:
                                   prompt = lens.template(FramedDecision, ReferenceClass)
                                   → LensCritique(verdict, reasoning, key_questions)
  ↓
[SYNTHESIZER]  assemble DecisionBrief
               run calibration checks (see §7)
               flag conflicts between lenses as features, not bugs
  ↓
RESPONSE TO USER
```

Each step has a typed contract. Each step is independently testable. See `/src/contracts.py`.

---

## 6. MVP scope

**Goal: a working end-to-end loop on 30 seed cases in 2 weeks of build time.**

### Phase 1 — Skeleton (week 1)
- [ ] Repo scaffolding (FastAPI backend, Next.js frontend, Postgres + pgvector)
- [ ] `Case` schema, migrations, seed loader
- [ ] 30 seed cases hand-written (covers the 6 domains, 5 cases each)
- [ ] Closed-vocabulary tag list finalized (~40 tags)
- [ ] 4 lens definitions written
- [ ] Framer module: prompt + JSON-schema validator
- [ ] Retriever module: embed + pgvector cosine search

### Phase 2 — Loop closure (week 2)
- [ ] Critic module: parallel lens calls
- [ ] Synthesizer: brief assembly
- [ ] Minimal UI: composer → brief viewer
- [ ] Calibration check #1: brief must cite ≥3 cases, must surface ≥1 disconfirming pattern
- [ ] 10-decision dogfood test with founders the team knows

### Out of scope for MVP
- IRL / MaxEnt anything
- Causal inference / DML / CATE
- Risk-appetite slider (Phase 3)
- Counterfactual simulation (Phase 4 — may never ship)
- User accounts (use share links)
- Payment

---

## 7. Evaluation — how we know it's not garbage

This is where most "AI advisor" products die. Three layers:

### 7.1 Process evals (run on every commit)
For 20 held-out test decisions, automatically check:
- Framer output validates against schema 100% of the time
- Retriever returns ≥5 cases for every test decision
- At least 2 of 4 lenses produce *materially different* critiques (measured by embedding distance between critiques)
- Brief contains ≥1 disconfirming case (a case in the reference class that contradicts the user's apparent leaning)

### 7.2 Decision-quality evals (run weekly)
A panel of 5 experienced operators reviews 10 anonymized briefs and scores on:
- **Steelmanning**: did the brief surface the strongest objection?
- **Reference-class fit**: are the retrieved cases actually analogous?
- **Heuristic specificity**: are the lens critiques specific to *this* decision or generic?
- **Calibration**: are claims of evidence proportionate to actual evidence?

Score is on a 1–5 rubric. Target: median ≥4 by week 6.

### 7.3 Outcome tracking (months, not weeks)
Users self-report decision outcomes at 90 / 180 / 365 days. We do **not** claim this proves the tool works — too many confounds. We use it for: (a) finding the briefs that, in hindsight, missed obvious risks, (b) growing the case library with user-contributed (consented) cases.

We never publish "X% of users using our tool succeeded" — that number would be survivorship bias laundered through a UI.

---

## 8. Non-stationarity & survivorship — how we handle them honestly

The original brief flagged these. The handling:

- **Survivorship bias in cases**: every case must have a *paired counterfactual signal* — what did at least one similar-position company do differently, and what happened? If we can't find one, the case is flagged "uncontrolled" and weighted lower.
- **Non-stationarity**: cases tagged with `era_dependence: high|medium|low` based on whether the decision context relied on regulatory regime, technology stack, or capital-cost environment that has materially shifted. The retriever down-weights `high` era-dependence cases unless the user's decision shares that regime.
- **Selection bias**: we openly tell users "you are seeing a curated 150-case library, not the universe of decisions." The brief shows the size of the matched reference class. If only 2 cases matched, we say so.

---

## 9. Risks & open questions

| Risk | Severity | Mitigation |
|---|---|---|
| LLM hallucinates "facts" about historical cases | High | All case content is human-curated and citation-backed; LLM only reasons over retrieved text. |
| Lens critiques converge to generic AI mush | High | Few-shot examples per lens; eval #7.1 tests for divergence. |
| Reference class too small to be useful | Medium | We disclose set size; below 4 cases we tell user "weak reference class." |
| Founders use brief as outsourced thinking | Medium | UI requires user to write their own decision rationale before seeing brief. |
| Legal: lawsuits over "advice" | Medium | T&C frame it as a research tool; no individualized financial/legal advice. |
| The whole thing is just a fancy search engine | Low — and that's fine | A great search engine over 150 curated decisions with a critique layer is a real product. |

---

## 10. Repo layout

```
success-directory/
├── README.md                    ← this file
├── docs/
│   ├── architecture.md          ← deeper system design
│   ├── data-model.md            ← schemas, vocab, examples
│   ├── lenses.md                ← all 4 lens specs
│   ├── eval-plan.md             ← detailed eval protocols
│   └── critique-of-original.md  ← the technical pushback on the IRL/CATE framing
├── src/
│   ├── contracts.py             ← typed I/O contracts between modules
│   ├── framer/
│   ├── retriever/
│   ├── critic/
│   ├── synthesizer/
│   └── api.py
├── prompts/
│   ├── framer.md
│   ├── lens_margin_of_safety.md
│   ├── lens_reversibility.md
│   ├── lens_concentration.md
│   └── lens_optionality.md
├── data/
│   ├── seed_cases/              ← 30 hand-written cases as YAML
│   ├── heuristic_vocab.yaml
│   └── lens_definitions.yaml
├── evals/
│   ├── test_decisions.yaml      ← 20 held-out test cases
│   ├── process_evals.py
│   └── decision_quality_rubric.md
└── notebooks/
    └── retrieval_quality.ipynb
```

---

## 11. What this document is NOT

It's not the full implementation. This README is the *constitution* — the thing the implementation has to stay loyal to.
