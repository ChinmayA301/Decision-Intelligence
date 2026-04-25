# Data Model

## Entities

### Case (the unit of value in the Pattern Library)

```python
class Case(BaseModel):
    case_id: str                          # slug: "netflix-qwikster-2011"
    title: str
    decision_maker: str
    organization: str
    year: int
    domain: Domain                        # enum, see below
    decision_type: DecisionType           # enum
    context_summary: str                  # 200-400 words, neutral
    options_considered: list[str]         # min 2
    option_taken: str
    stated_rationale: str | None
    inferred_heuristics: list[Heuristic]  # closed vocab, see /data/heuristic_vocab.yaml
    constraints_at_time: list[Constraint]
    outcome_12mo: str                     # narrative
    outcome_36mo: str | None
    outcome_label: OutcomeLabel           # enum
    counterfactual_signal: str | None     # what comparable peers did
    era_dependence: EraDependence         # high | medium | low
    sources: list[Citation]               # min 2
    embedding: list[float]                # 1024 or 1536 dim
    review_status: ReviewStatus           # draft | reviewed | published
    created_at: datetime
    reviewed_by: str | None
```

### Enums

```python
class Domain(str, Enum):
    PRICING = "pricing"
    M_AND_A = "m_and_a"
    MARKET_ENTRY = "market_entry"
    KEY_HIRE = "key_hire"
    PRODUCT_SUNSET = "product_sunset"
    CAPITAL_ALLOCATION = "capital_allocation"

class DecisionType(str, Enum):
    REVERSIBLE = "reversible"           # two-way door
    ONE_WAY = "one_way"                 # hard to reverse
    SEQUENTIAL = "sequential"           # commits to a path of further decisions

class OutcomeLabel(str, Enum):
    SUCCESS = "success"
    MIXED = "mixed"
    FAILURE = "failure"
    TOO_EARLY = "too_early"

class EraDependence(str, Enum):
    HIGH = "high"      # depends on regulatory/tech regime that has shifted
    MEDIUM = "medium"
    LOW = "low"        # decision logic largely transferable
```

### Citation

```python
class Citation(BaseModel):
    type: Literal["book", "article", "filing", "interview", "primary_doc"]
    title: str
    author: str | None
    year: int
    url: str | None
    pages: str | None    # "pp. 234-241"
    quote: str | None    # supporting excerpt, ≤30 words
```

## Heuristic vocabulary (the closed tag set)

Stored in `/data/heuristic_vocab.yaml`. ~40 tags. Initial list:

```yaml
risk_posture:
  - margin_of_safety
  - asymmetric_payoff
  - barbell_allocation
  - downside_minimization

speed_and_consensus:
  - speed_over_consensus
  - consensus_required
  - decisive_under_uncertainty
  - structured_deliberation

reversibility:
  - reversibility_first
  - one_way_door_acceptance
  - optionality_preserve
  - commit_and_kill

resource_strategy:
  - cash_runway_priority
  - capital_efficiency
  - growth_at_cost
  - vertical_integration
  - horizontal_focus

talent_and_org:
  - talent_density_bet
  - founder_mode
  - delegation_first
  - cultural_homogeneity
  - cultural_diversity_bet

market_posture:
  - first_mover
  - fast_follower
  - platform_neutrality
  - exclusive_partnership
  - regulatory_arbitrage
  - regulatory_compliance_first

narrative_and_signal:
  - narrative_control
  - transparent_communication
  - stealth_mode
  - brand_protection_priority

competitive:
  - concentration_bet
  - diversification_bet
  - moat_widening
  - asymmetric_competition
```

**Rules for the vocab:**
- Every tag has a 2-sentence definition in the YAML
- New tags require review (PR with at least 2 cases that needed it)
- Tags should be roughly orthogonal (one case might have 3-5 tags)

## Lens definitions

Stored in `/data/lens_definitions.yaml`.

```yaml
margin_of_safety:
  display_name: "Margin-of-Safety Lens"
  inspired_by: ["Buffett", "Graham", "Munger"]
  priority_heuristics:
    - margin_of_safety: 1.0
    - downside_minimization: 0.9
    - cash_runway_priority: 0.7
    - reversibility_first: 0.5
  disqualifying_heuristics:
    - growth_at_cost
    - concentration_bet
  decision_emphasis: "What is the worst plausible outcome and can the org survive it?"
  prompt_template_path: "prompts/lens_margin_of_safety.md"

reversibility:
  display_name: "Reversibility Lens"
  inspired_by: ["Bezos"]
  priority_heuristics:
    - reversibility_first: 1.0
    - optionality_preserve: 0.9
    - structured_deliberation: 0.6
  disqualifying_heuristics: []
  decision_emphasis: "Is this a one-way door, and if so, have we paid the cost of slowness?"
  prompt_template_path: "prompts/lens_reversibility.md"

concentration:
  display_name: "Concentration Lens"
  inspired_by: ["Jobs", "Thiel"]
  priority_heuristics:
    - concentration_bet: 1.0
    - decisive_under_uncertainty: 0.8
    - founder_mode: 0.7
    - asymmetric_payoff: 0.6
  disqualifying_heuristics:
    - barbell_allocation
    - diversification_bet
  decision_emphasis: "If we are right, is the upside large enough to justify a focused bet?"
  prompt_template_path: "prompts/lens_concentration.md"

optionality:
  display_name: "Optionality Lens"
  inspired_by: ["Taleb"]
  priority_heuristics:
    - optionality_preserve: 1.0
    - barbell_allocation: 0.8
    - asymmetric_payoff: 0.7
  disqualifying_heuristics:
    - one_way_door_acceptance
    - concentration_bet
  decision_emphasis: "Does this preserve our ability to respond to information we don't yet have?"
  prompt_template_path: "prompts/lens_optionality.md"
```

## Postgres schema (DDL preview)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE cases (
    case_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    decision_maker TEXT NOT NULL,
    organization TEXT NOT NULL,
    year INT NOT NULL,
    domain TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    context_summary TEXT NOT NULL,
    options_considered JSONB NOT NULL,
    option_taken TEXT NOT NULL,
    stated_rationale TEXT,
    inferred_heuristics JSONB NOT NULL,
    constraints_at_time JSONB,
    outcome_12mo TEXT NOT NULL,
    outcome_36mo TEXT,
    outcome_label TEXT NOT NULL,
    counterfactual_signal TEXT,
    era_dependence TEXT NOT NULL,
    sources JSONB NOT NULL,
    embedding vector(1024),
    review_status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ DEFAULT now(),
    reviewed_by TEXT
);

CREATE INDEX cases_domain_idx ON cases(domain);
CREATE INDEX cases_decision_type_idx ON cases(decision_type);
CREATE INDEX cases_outcome_idx ON cases(outcome_label);
CREATE INDEX cases_embedding_idx ON cases USING hnsw (embedding vector_cosine_ops);

CREATE TABLE briefs (
    brief_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_input TEXT NOT NULL,
    framed_decision JSONB NOT NULL,
    reference_class JSONB NOT NULL,
    lens_critiques JSONB NOT NULL,
    final_brief JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    user_id UUID  -- nullable for MVP (no accounts)
);
```

## Required guarantees

1. **No case enters the library without 2+ citations.** Enforced at insert time.
2. **No case is published without `review_status = 'reviewed'` and a `reviewed_by` value.** Enforced at retrieval time (retriever filters `WHERE review_status = 'reviewed'`).
3. **Embeddings are recomputed when `context_summary` changes.** Enforced via trigger or pre-commit hook.
4. **Heuristic tags must be in the closed vocabulary.** Enforced by JSONB validation.
