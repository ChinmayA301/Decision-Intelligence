"""
Typed I/O contracts between modules.

Every module in the reasoning loop reads and writes one of these.
This is the source of truth for what each step is committing to produce.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────
# Enums (mirror /docs/data-model.md)
# ─────────────────────────────────────────────────────────────────────

class Domain(str, Enum):
    PRICING = "pricing"
    M_AND_A = "m_and_a"
    MARKET_ENTRY = "market_entry"
    KEY_HIRE = "key_hire"
    PRODUCT_SUNSET = "product_sunset"
    CAPITAL_ALLOCATION = "capital_allocation"


class DecisionType(str, Enum):
    REVERSIBLE = "reversible"
    ONE_WAY = "one_way"
    SEQUENTIAL = "sequential"


class OutcomeLabel(str, Enum):
    SUCCESS = "success"
    MIXED = "mixed"
    FAILURE = "failure"
    TOO_EARLY = "too_early"


class EraDependence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LensVerdict(str, Enum):
    ENDORSES = "endorses"
    ENDORSES_WITH_CAVEATS = "endorses_with_caveats"
    REJECTS = "rejects"
    ABSTAINS = "abstains"


# ─────────────────────────────────────────────────────────────────────
# Framer output
# ─────────────────────────────────────────────────────────────────────

class FramedDecision(BaseModel):
    """The Framer's structured restatement of the user's decision.

    Hard rule: if the Framer cannot fill these fields confidently from the
    user's input, it returns clarifying_questions instead and the API
    bounces back to the UI without proceeding to retrieval.
    """
    choice_being_made: str = Field(
        description="One sentence describing the actual choice. Should be binary or small-discrete."
    )
    alternatives: list[str] = Field(
        min_length=2,
        description="At least 2, including the do-nothing option where applicable."
    )
    domain: Domain
    decision_type: DecisionType
    time_horizon_months: int = Field(
        gt=0,
        description="Over what horizon does success/failure manifest?"
    )
    key_uncertainties: list[str] = Field(
        min_length=1,
        max_length=5,
        description="The things the user genuinely doesn't know."
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Capital, talent, regulatory, competitive, etc."
    )
    user_apparent_leaning: str | None = Field(
        default=None,
        description="If the user signaled which option they're leaning toward; used for "
                    "disconfirmation matching."
    )
    context_summary: str = Field(
        description="2-4 sentence neutral restatement, used for retrieval embedding."
    )

    @field_validator("alternatives")
    @classmethod
    def alternatives_distinct(cls, v: list[str]) -> list[str]:
        if len(set(map(str.strip, v))) != len(v):
            raise ValueError("alternatives must be distinct")
        return v


class FramerClarification(BaseModel):
    """Returned when the Framer can't responsibly structure the input."""
    reason: str
    clarifying_questions: list[str] = Field(min_length=1, max_length=3)


FramerOutput = FramedDecision | FramerClarification


# ─────────────────────────────────────────────────────────────────────
# Retriever output
# ─────────────────────────────────────────────────────────────────────

class RetrievedCase(BaseModel):
    case_id: str
    title: str
    year: int
    organization: str
    decision_maker: str
    domain: Domain
    decision_type: DecisionType
    similarity: float = Field(ge=0.0, le=1.0)
    outcome_label: OutcomeLabel
    era_dependence: EraDependence
    snippet: str = Field(description="200-word excerpt for display + critic context")


class BaseRate(BaseModel):
    n: int
    success: int
    mixed: int
    failure: int
    too_early: int

    @property
    def success_rate(self) -> float | None:
        decided = self.success + self.mixed + self.failure
        if decided == 0:
            return None
        return self.success / decided


class ReferenceClass(BaseModel):
    cases: list[RetrievedCase] = Field(max_length=10)
    base_rate: BaseRate
    weak_reference_class: bool = Field(
        description="True if fewer than 4 cases matched after filters."
    )

    @field_validator("weak_reference_class", mode="before")
    @classmethod
    def auto_set_weak(cls, v: bool, info) -> bool:
        # Allow explicit override but compute default from data
        cases = info.data.get("cases", [])
        return v if v is not None else (len(cases) < 4)


# ─────────────────────────────────────────────────────────────────────
# Critic output
# ─────────────────────────────────────────────────────────────────────

class LensCritique(BaseModel):
    lens_id: str
    lens_display_name: str
    verdict: LensVerdict
    reasoning: str = Field(
        description="3-5 sentences. Specific to the user's decision, not generic."
    )
    key_questions: list[str] = Field(
        min_length=1,
        max_length=3,
        description="Questions the user must answer before proceeding."
    )
    most_relevant_case_ids: list[str] = Field(
        max_length=4,
        description="From the ReferenceClass; used to cross-check against hallucination."
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description="How well does this lens apply to this decision?"
    )


# ─────────────────────────────────────────────────────────────────────
# Synthesizer output (the final user-facing artifact)
# ─────────────────────────────────────────────────────────────────────

class DecisionBrief(BaseModel):
    brief_id: str
    framed_decision: FramedDecision
    reference_class: ReferenceClass
    lens_critiques: list[LensCritique] = Field(min_length=4, max_length=4)
    tension_summary: str = Field(
        description="2 sentences: where the lenses disagreed and why."
    )
    pre_mortem: list[str] = Field(
        min_length=2,
        max_length=5,
        description="Drawn from failure cases in the reference class."
    )
    cited_case_ids: list[str] = Field(
        description="Union of all most_relevant_case_ids; used by UI for citation links."
    )
    calibration_notes: list[str] = Field(
        default_factory=list,
        description="Honesty surface: 'reference class is small', 'all lenses converged', etc."
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────────
# Module signatures (for type hints in implementations)
# ─────────────────────────────────────────────────────────────────────

class FramerProtocol:
    async def frame(self, raw_user_input: str) -> FramerOutput: ...


class RetrieverProtocol:
    async def retrieve(self, decision: FramedDecision) -> ReferenceClass: ...


class CriticProtocol:
    async def critique(
        self, decision: FramedDecision, refs: ReferenceClass
    ) -> list[LensCritique]: ...


class SynthesizerProtocol:
    async def synthesize(
        self,
        decision: FramedDecision,
        refs: ReferenceClass,
        critiques: list[LensCritique],
    ) -> DecisionBrief: ...
