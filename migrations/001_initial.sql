-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Cases: the unit of value in the Pattern Library
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    decision_maker TEXT NOT NULL,
    organization TEXT NOT NULL,
    year INT NOT NULL,
    domain TEXT NOT NULL CHECK (domain IN ('pricing','m_and_a','market_entry','key_hire','product_sunset','capital_allocation')),
    decision_type TEXT NOT NULL CHECK (decision_type IN ('reversible','one_way','sequential')),
    context_summary TEXT NOT NULL,
    options_considered JSONB NOT NULL,
    option_taken TEXT NOT NULL,
    stated_rationale TEXT,
    inferred_heuristics JSONB NOT NULL DEFAULT '[]',
    constraints_at_time JSONB DEFAULT '[]',
    outcome_12mo TEXT NOT NULL,
    outcome_36mo TEXT,
    outcome_label TEXT NOT NULL CHECK (outcome_label IN ('success','mixed','failure','too_early')),
    counterfactual_signal TEXT,
    era_dependence TEXT NOT NULL CHECK (era_dependence IN ('high','medium','low')),
    sources JSONB NOT NULL,
    embedding vector(1024),
    review_status TEXT NOT NULL DEFAULT 'draft' CHECK (review_status IN ('draft','reviewed','published')),
    created_at TIMESTAMPTZ DEFAULT now(),
    reviewed_by TEXT
);

CREATE INDEX IF NOT EXISTS cases_domain_idx ON cases(domain);
CREATE INDEX IF NOT EXISTS cases_decision_type_idx ON cases(decision_type);
CREATE INDEX IF NOT EXISTS cases_outcome_idx ON cases(outcome_label);
CREATE INDEX IF NOT EXISTS cases_review_status_idx ON cases(review_status);
CREATE INDEX IF NOT EXISTS cases_embedding_idx ON cases USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Briefs: the output artifact stored for share links
CREATE TABLE IF NOT EXISTS briefs (
    brief_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_input TEXT NOT NULL,
    framed_decision JSONB NOT NULL,
    reference_class JSONB NOT NULL,
    lens_critiques JSONB NOT NULL,
    final_brief JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    user_id UUID  -- nullable for MVP (no accounts)
);

CREATE INDEX IF NOT EXISTS briefs_created_at_idx ON briefs(created_at DESC);
