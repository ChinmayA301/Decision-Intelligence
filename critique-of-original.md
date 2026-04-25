# Critique of the original KT brief

This document exists so that anyone joining the project understands *why* the implementation departs from the original technical framing. It is not a takedown of the brief — the brief was a useful provocation. But shipping it as written would burn 6+ months on math that doesn't fit the data.

## The core problem
The original brief proposed **three** mathematical engines (IRL, Causal CATE, Bayesian Fusion). Each requires data that does not exist in usable form for strategic business decisions.

## Engine-by-engine

### A. MaxEnt IRL — "recover the reward function of an expert"

**The math is real.** Ziebart et al. 2008. It works beautifully when you have:
- Many trajectories from one expert
- A well-defined state space
- Discrete or low-dimensional action space
- Repeatable environments

**Why it doesn't fit here:**
1. Steve Jobs made maybe 200 decisions in his career that anyone has documented. That's not a trajectory dataset; that's a magazine profile.
2. The "state" of a strategic decision is not a vector — it's a story. Embedding it loses exactly the structure IRL needs to reason over.
3. Even if you fit a $\theta$, you can't validate it. There's no held-out trajectory.
4. What you'll actually get: a $\theta$ that is whatever your prompt-engineered context selection happened to emphasize. Confirmation bias with extra steps.

**What we do instead:** Hand-tag heuristics from a closed vocabulary. A human + LLM reads the case and says "this looks like `margin_of_safety` and `concentration_bet`." We can audit that. We can disagree with that. It is honest tagging, not a fake reward function.

### B. CATE / Double Machine Learning — "estimate causal treatment effect of a decision"

**The math is real.** Chernozhukov et al. 2018. DML is the right tool for estimating heterogeneous treatment effects in observational data when you have:
- Many units that did and did not receive treatment
- Overlap (positivity) between treated and control populations
- Plausibly sufficient adjustment for confounders

**Why it doesn't fit here:**
1. "Should we acquire competitor X" is n=1. There is no control group of "this same company in this same week with the same cash position not acquiring competitor X."
2. Even where n>1 (e.g., "did your last pricing increase work"), the confounders are largely *unobserved* — internal politics, customer perception, sales-team morale.
3. DML on small-n strategic decisions produces confidence intervals so wide they swallow any conclusion. The honest output is "we don't know."

**What we do instead:** Reference-class forecasting. Show the user 5–10 structurally similar past decisions and let them see the distribution of outcomes. It's the *outside view* (Kahneman). It's empirically the best correction we have for planning fallacy.

Where CATE *does* fit and we may use it later: sub-decisions inside a domain where there's actual data (e.g., "should I A/B test this pricing change before rolling out broadly"). That's not v1.

### C. Bayesian Fusion — multiplying causal and instinct posteriors

The equation in the brief:
$$P(\text{Success}|D, C) \propto P(O|D, C)_{\text{Causal}} \times P(D|C, \pi_{\text{expert}})_{\text{Instinct}}$$

**Why it doesn't compose:**
1. The two terms aren't conditionally independent given $C$. The same context drove both the expert's choice and the outcome.
2. Neither term is well-calibrated, so multiplying them produces a number that looks like a probability but isn't.
3. Users will read the output number as "the AI says I have a 73% chance of success." That number is a lie.

**What we do instead:** No fused score. The Decision Brief shows two parallel things:
- **Reference-class base rate** with its sample size and confidence interval
- **Heuristic critiques** from the lenses, with the trade-offs they highlight

The user does the integration. That's the right division of labor.

## The non-mathematical issues with the original brief

1. **No definition of "success."** Successful for whom? On what time horizon? The brief gestures at this but doesn't pin it down.
2. **"Decision DNA" is a marketing phrase, not a technical concept.** Reward weights from IRL are not DNA. They're regression coefficients on hand-engineered features in a model that may not have converged.
3. **"Expert Board" of Jobs / Buffett / Iger** is a UX trap. It positions the tool as oracle-roleplay rather than a thinking aid. We pivot to *named lenses* (the heuristic, not the human).
4. **Section 6's "next steps" are a research program, not an MVP.** Vector DBs of decision-action-outcome triplets at scale require labeling infrastructure that takes years to build. The MVP works on 30 cases.

## What the original brief got right (and we kept)

- The framing of decision intelligence as **augmenting human reasoning, not replacing it** — yes.
- The instinct that **historical patterns matter under uncertainty** — yes, that's reference-class forecasting and it's well-supported.
- **Survivorship / selection / non-stationarity** as first-class concerns — yes; we address each in §8 of the README.
- The **modular separation** of framing, retrieval, critique — kept and made explicit in the contracts.

## TL;DR

The original brief tried to solve the problem with the most impressive math available. The right approach is the *most appropriate* math: structured retrieval over a curated case library, honest tagging instead of fake reward learning, and reference classes instead of fake causal scores.

The product is no less ambitious. It's more shippable.
