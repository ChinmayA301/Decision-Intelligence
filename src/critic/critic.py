"""Critic module — runs all 4 lenses in parallel and returns list[LensCritique]."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import anthropic
from pydantic import ValidationError

from src.contracts import FramedDecision, LensCritique, LensVerdict, ReferenceClass

_MODEL = "claude-sonnet-4-6"
_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

LENS_IDS = ["margin_of_safety", "reversibility", "concentration", "optionality"]
_LENS_PROMPT_PATHS = {
    "margin_of_safety": _PROMPTS_DIR / "lens_margin_of_safety.md",
    "reversibility": _PROMPTS_DIR / "lens_reversibility.md",
    "concentration": _PROMPTS_DIR / "lens_concentration.md",
    "optionality": _PROMPTS_DIR / "lens_optionality.md",
}
_LENS_TEMPLATES: dict[str, str] = {
    lens_id: path.read_text()
    for lens_id, path in _LENS_PROMPT_PATHS.items()
}


def _build_critic_user_message(
    decision: FramedDecision,
    refs: ReferenceClass,
) -> str:
    cases_text = "\n".join(
        f"- [{c.case_id}] {c.title} ({c.year}): {c.outcome_label.value}. {c.snippet[:300]}"
        for c in refs.cases
    )
    base = refs.base_rate
    return (
        f"## Framed Decision\n\n"
        f"Choice: {decision.choice_being_made}\n"
        f"Domain: {decision.domain.value}\n"
        f"Decision type: {decision.decision_type.value}\n"
        f"Time horizon: {decision.time_horizon_months} months\n"
        f"Alternatives:\n"
        + "\n".join(f"  - {a}" for a in decision.alternatives)
        + f"\nKey uncertainties:\n"
        + "\n".join(f"  - {u}" for u in decision.key_uncertainties)
        + (f"\nUser's apparent leaning: {decision.user_apparent_leaning}" if decision.user_apparent_leaning else "")
        + f"\nConstraints: {', '.join(decision.constraints) if decision.constraints else 'none stated'}"
        + f"\n\n## Reference Class\n\n"
        f"n={base.n}, success={base.success}, mixed={base.mixed}, failure={base.failure}, too_early={base.too_early}\n\n"
        f"Cases (use ONLY these case_ids in most_relevant_case_ids):\n{cases_text}\n\n"
        "Return ONLY the JSON object described in your instructions. No other text."
    )


def _parse_lens_response(text: str, expected_lens_id: str) -> LensCritique:
    content = text.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])

    data = json.loads(content)
    # Ensure lens_id matches what we expected
    data["lens_id"] = expected_lens_id
    return LensCritique.model_validate(data)


async def _run_single_lens(
    client: anthropic.AsyncAnthropic,
    lens_id: str,
    decision: FramedDecision,
    refs: ReferenceClass,
) -> LensCritique:
    system_prompt = _LENS_TEMPLATES[lens_id]
    user_message = _build_critic_user_message(decision, refs)

    for attempt in range(2):
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = response.content[0].text
        try:
            critique = _parse_lens_response(raw_text, lens_id)
            # Validate that all cited case_ids exist in the reference class
            valid_ids = {c.case_id for c in refs.cases}
            critique.most_relevant_case_ids = [
                cid for cid in critique.most_relevant_case_ids if cid in valid_ids
            ]
            return critique
        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            if attempt == 0:
                # One retry with error feedback
                user_message = (
                    user_message
                    + f"\n\nYour previous response was invalid: {exc}\n"
                    "Return corrected JSON only."
                )
            else:
                # Fallback: return abstains critique
                return LensCritique(
                    lens_id=lens_id,
                    lens_display_name=_lens_display_name(lens_id),
                    verdict=LensVerdict.ABSTAINS,
                    reasoning=f"Lens could not produce valid output after retries ({exc}).",
                    key_questions=["Please retry your analysis with a more specific decision framing."],
                    most_relevant_case_ids=[],
                    confidence="low",
                )

    # Should be unreachable
    raise RuntimeError(f"Lens {lens_id} failed unexpectedly")


def _lens_display_name(lens_id: str) -> str:
    names = {
        "margin_of_safety": "Margin-of-Safety Lens",
        "reversibility": "Reversibility Lens",
        "concentration": "Concentration Lens",
        "optionality": "Optionality Lens",
    }
    return names.get(lens_id, lens_id)


class Critic:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )

    async def critique(
        self, decision: FramedDecision, refs: ReferenceClass
    ) -> list[LensCritique]:
        tasks = [
            _run_single_lens(self._client, lens_id, decision, refs)
            for lens_id in LENS_IDS
        ]
        return list(await asyncio.gather(*tasks))
