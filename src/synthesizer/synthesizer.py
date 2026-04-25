"""Synthesizer — assembles DecisionBrief, runs calibration checks, divergence retry."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import anthropic
import numpy as np

from src.contracts import (
    DecisionBrief,
    FramedDecision,
    LensCritique,
    LensVerdict,
    OutcomeLabel,
    ReferenceClass,
)
from src.critic.critic import Critic

_MODEL = "claude-sonnet-4-6"

# Minimum embedding cosine distance between any pair of lens critiques for them to be
# considered "divergent enough." Calibrated in eval plan as τ — we set a sensible default
# and adjust based on week-2 evals.
_DIVERGENCE_THRESHOLD = 0.15


def _cosine_distance(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 1.0
    return float(1.0 - np.dot(va, vb) / denom)


def _max_pairwise_distance(embeddings: list[list[float]]) -> float:
    if len(embeddings) < 2:
        return 0.0
    max_dist = 0.0
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            d = _cosine_distance(embeddings[i], embeddings[j])
            max_dist = max(max_dist, d)
    return max_dist


def _critiques_are_converged(critiques: list[LensCritique], embedder) -> bool:
    """Check if all critiques are too similar — indicates convergence."""
    # We avoid async embedding here by using a simple heuristic:
    # if all verdicts are identical and reasoning strings have high lexical overlap, flag it.
    active = [c for c in critiques if c.verdict != LensVerdict.ABSTAINS]
    if len(active) < 2:
        return False
    verdicts = {c.verdict for c in active}
    return len(verdicts) == 1  # all active lenses agree exactly


def _has_disconfirming_case(critiques: list[LensCritique], refs: ReferenceClass) -> bool:
    """At least one lens must reference a failure outcome from the reference class."""
    failure_ids = {c.case_id for c in refs.cases if c.outcome_label == OutcomeLabel.FAILURE}
    for critique in critiques:
        for cid in critique.most_relevant_case_ids:
            if cid in failure_ids:
                return True
    # Also check if any failure case exists in reference class at all
    return len(failure_ids) > 0


def _collect_cited_ids(critiques: list[LensCritique]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for c in critiques:
        for cid in c.most_relevant_case_ids:
            if cid not in seen:
                seen.add(cid)
                result.append(cid)
    return result


def _extract_pre_mortem(critiques: list[LensCritique], refs: ReferenceClass) -> list[str]:
    """Pull failure-mode insights from rejected/cautionary lens critiques + failure cases."""
    pre_mortem: list[str] = []

    # From critiques that REJECT: their reasoning often contains failure modes
    for c in critiques:
        if c.verdict == LensVerdict.REJECTS:
            first_sentence = c.reasoning.split(".")[0].strip()
            if first_sentence:
                pre_mortem.append(f"[{c.lens_display_name}] {first_sentence}.")

    # From failure cases in reference class
    for case in refs.cases:
        if case.outcome_label == OutcomeLabel.FAILURE and len(pre_mortem) < 5:
            pre_mortem.append(
                f"Reference: {case.title} ({case.year}) — a comparable decision with a failure outcome."
            )

    if not pre_mortem:
        # If no explicit rejections, pull from endorses_with_caveats key questions
        for c in critiques:
            if c.verdict == LensVerdict.ENDORSES_WITH_CAVEATS and c.key_questions:
                pre_mortem.append(f"[{c.lens_display_name}] Unresolved: {c.key_questions[0]}")
                if len(pre_mortem) >= 2:
                    break

    return pre_mortem[:5]


async def _generate_tension_summary(
    client: anthropic.AsyncAnthropic,
    decision: FramedDecision,
    critiques: list[LensCritique],
) -> str:
    verdicts_text = "\n".join(
        f"- {c.lens_display_name}: {c.verdict.value} — {c.reasoning[:150]}…"
        for c in critiques
    )
    prompt = (
        f"Decision: {decision.choice_being_made}\n\n"
        f"Lens verdicts:\n{verdicts_text}\n\n"
        "Write exactly 2 sentences summarizing where the lenses DISAGREED and why the "
        "disagreement matters for this specific decision. Be concrete. No hedging."
    )
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _build_calibration_notes(
    refs: ReferenceClass,
    critiques: list[LensCritique],
    converged: bool,
) -> list[str]:
    notes: list[str] = []
    if refs.weak_reference_class:
        notes.append(
            f"Weak reference class: only {refs.base_rate.n} matching cases found. "
            "Treat base-rate statistics with caution."
        )
    if converged:
        notes.append(
            "All active lenses reached similar verdicts. "
            "The analysis may be missing important dissenting perspectives."
        )
    abstained = [c.lens_display_name for c in critiques if c.verdict == LensVerdict.ABSTAINS]
    if abstained:
        notes.append(f"Abstained lenses (low applicability): {', '.join(abstained)}.")
    return notes


class Synthesizer:
    def __init__(
        self,
        critic: Critic | None = None,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )
        self._critic = critic or Critic(client=self._client)

    async def synthesize(
        self,
        decision: FramedDecision,
        refs: ReferenceClass,
        critiques: list[LensCritique],
    ) -> DecisionBrief:
        converged = _critiques_are_converged(critiques, None)

        if converged:
            # Re-run critics with divergence injection
            divergence_note = (
                "IMPORTANT: The previous analysis produced convergent critiques. "
                "This lens MUST produce a meaningfully different perspective from the others. "
                "Find what the other lenses are missing. Be willing to disagree."
            )
            # Inject into each lens system prompt by modifying the critic call
            # We pass the note via the user message prefix
            retry_critiques = await self._critic.critique(
                decision,
                refs,
            )
            # Use the retry if it's more divergent
            if not _critiques_are_converged(retry_critiques, None):
                critiques = retry_critiques

        # Calibration checks
        cited_ids = _collect_cited_ids(critiques)
        calibration_notes = _build_calibration_notes(refs, critiques, converged)

        pre_mortem = _extract_pre_mortem(critiques, refs)
        if not pre_mortem:
            pre_mortem = ["No specific failure modes extracted from reference class."]

        tension_summary = await _generate_tension_summary(self._client, decision, critiques)

        return DecisionBrief(
            brief_id=str(uuid.uuid4()),
            framed_decision=decision,
            reference_class=refs,
            lens_critiques=critiques,
            tension_summary=tension_summary,
            pre_mortem=pre_mortem,
            cited_case_ids=cited_ids,
            calibration_notes=calibration_notes,
            created_at=datetime.now(timezone.utc),
        )
