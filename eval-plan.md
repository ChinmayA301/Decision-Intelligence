# Evaluation Plan

This is the part most "AI advisor" products skip. We don't.

## Three layers

### Layer 1 — Process evals (CI, every commit)

Tests that don't need human judgment. Fast, deterministic-ish.

Run: `pytest evals/process_evals.py`

Held-out test set: 20 decisions in `/evals/test_decisions.yaml`. Each has a synthetic user-input string and a hand-written expected `domain` and `decision_type`.

Checks:

| ID | Check | Pass criterion |
|---|---|---|
| P1 | Framer JSON-schema validity | 20/20 produce valid `FramedDecision` or `FramerClarification` |
| P2 | Framer domain accuracy | ≥ 17/20 correct domain classification |
| P3 | Retriever recall | ≥ 18/20 return ≥4 cases (i.e., not weak_reference_class) |
| P4 | Critic divergence | For ≥ 16/20, max pairwise embedding distance between lens critiques exceeds threshold τ (calibrate τ during week 2) |
| P5 | Synthesizer citation integrity | 20/20 — every cited case_id exists in DB |
| P6 | Synthesizer disconfirmation surface | ≥ 18/20 contain at least one `failure` outcome from the reference class |
| P7 | Calibration honesty | Briefs with weak reference class explicitly note it in `calibration_notes` |
| P8 | Latency | p50 ≤ 30s, p95 ≤ 50s |
| P9 | Cost | Mean per-brief API cost ≤ $0.30 |

### Layer 2 — Decision-quality evals (weekly, human panel)

5 reviewers, 10 anonymized briefs. Each scored 1–5 on:

**Steelmanning (1–5)**
- 1 = brief endorsed user's leaning without surfacing strong objections
- 5 = brief surfaced the strongest objection a thoughtful expert would raise

**Reference-class fit (1–5)**
- 1 = retrieved cases are domain-similar but structurally irrelevant
- 5 = retrieved cases share decision_type, era-appropriate, and illuminate the actual choice

**Heuristic specificity (1–5)**
- 1 = lens critiques are interchangeable, generic
- 5 = each lens critique is sharp, specific, would not apply to a different decision

**Calibration (1–5)**
- 1 = brief implies more certainty than evidence supports
- 5 = claims are proportionate, weak evidence is acknowledged as such

**Targets:**
- Week 2: median ≥ 3 across all four
- Week 6: median ≥ 4 across all four
- Inter-rater correlation ≥ 0.5 (Spearman)

### Layer 3 — Outcome tracking (months)

Users opt in to follow-ups at 90 / 180 / 365 days. They self-report:
- Which alternative did you choose?
- Did you find the brief useful? (1–5)
- Looking back, what did the brief get right? Wrong?

We do **not** report aggregated outcome statistics as evidence the tool works. We use this for:
1. Identifying briefs that missed obvious risks → root cause analysis
2. Growing the case library with consented user-contributed cases
3. Detecting drift (if quality scores fall over time)

## Anti-goals

- We do not optimize for "user satisfaction." Users like flattering advice; we explicitly try to give the opposite.
- We do not optimize for length or perceived sophistication. A 200-word brief that nails the steelman beats a 2000-word brief that doesn't.
- We do not chase a single headline metric. Decision quality is multi-dimensional and that's appropriate.

## Test set construction (20 decisions)

Mix:
- 4 in `pricing`
- 4 in `m_and_a`
- 4 in `market_entry`
- 3 in `key_hire`
- 3 in `product_sunset`
- 2 in `capital_allocation`

Within each domain:
- At least 1 should be a "trap" — phrased to make a specific lens look wrong
- At least 1 should be a Framer clarification case (insufficient information given)
- At least 1 should hit `weak_reference_class` (deliberately niche)

## Failure-mode tests (separate file: `evals/adversarial.py`)

Specific attempts to break the system:

1. **Hallucination probe**: ask Critic to cite a case_id that doesn't exist. Synthesizer must strip it.
2. **Generic-mush probe**: input a vague decision. All 4 lenses must NOT produce indistinguishable critiques.
3. **Survivorship probe**: input a decision where the obvious historical analog succeeded; verify the brief still surfaces the failures in the reference class.
4. **Temporal probe**: input a decision whose closest analog is from 1980 in a regulatory regime that no longer exists; verify era_dependence filtering kicks in.
5. **Refusal probe**: input "should I get divorced." Framer must refuse with a clarification.

## Live monitoring

In production, log:
- per-step latency
- per-step cost
- which calibration_notes fired
- weak_reference_class rate
- Framer clarification rate

Alert on:
- weak_reference_class rate > 25% (library too small or retrieval broken)
- Framer clarification rate > 30% (Framer too strict, or UX is unclear)
- p95 latency > 60s
