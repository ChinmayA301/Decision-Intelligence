"""Tests for the zero-database backends: LocalCaseStore + LocalBriefStore.

These run with no API keys and no Postgres — synthetic embeddings only.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest

from src.contracts import (
    BaseRate,
    DecisionBrief,
    DecisionType,
    Domain,
    EraDependence,
    FramedDecision,
    LensCritique,
    LensVerdict,
    OutcomeLabel,
    ReferenceClass,
    RetrievedCase,
)
from src.retriever.retriever import Retriever
from src.store.brief_store import LocalBriefStore
from src.store.case_store import LocalCaseStore

_DIM = 8


def _unit(i: int) -> list[float]:
    v = [0.0] * _DIM
    v[i % _DIM] = 1.0
    return v


def _case(i: int, domain: str = "market_entry", status: str = "reviewed") -> dict:
    return {
        "case_id": f"case-{i}",
        "title": f"Case {i}",
        "year": 2000 + i,
        "organization": f"Org {i}",
        "decision_maker": f"CEO {i}",
        "domain": domain,
        "decision_type": "one_way",
        "outcome_label": ["success", "mixed", "failure", "too_early"][i % 4],
        "era_dependence": "low",
        "context_summary": f"Context for case {i}. " * 10,
        "option_taken": f"Option {i}",
        "review_status": status,
        "sources": ["https://a.example", "https://b.example"],
        "embedding": _unit(i),
    }


@pytest.fixture()
def store_path(tmp_path: Path) -> Path:
    cases = [_case(i) for i in range(6)]
    cases.append(_case(6, domain="pricing"))
    cases.append(_case(7, status="draft"))  # must be excluded
    path = tmp_path / "case_store.json"
    path.write_text(json.dumps({"version": 1, "cases": cases}))
    return path


class FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_unit(0) for _ in texts]

    async def embed_one(self, text: str) -> list[float]:
        return _unit(0)


def _framed() -> FramedDecision:
    return FramedDecision(
        choice_being_made="Enter the new market now or wait a year.",
        alternatives=["Enter now", "Wait a year", "Do nothing"],
        domain=Domain.MARKET_ENTRY,
        decision_type=DecisionType.ONE_WAY,
        time_horizon_months=24,
        key_uncertainties=["competitor response"],
        constraints=["limited capital"],
        context_summary="A company is weighing whether to enter a new market.",
    )


def test_local_store_excludes_drafts_and_ranks_by_similarity(store_path: Path) -> None:
    store = LocalCaseStore(store_path)
    assert len(store) == 7  # 8 written, 1 draft excluded

    rows = asyncio.run(store.fetch_candidates(_unit(0), "market_entry"))
    assert all(r["domain"] == "market_entry" for r in rows)
    # case-0 has the identical embedding, so it must rank first with sim ~1.
    assert rows[0]["case_id"] == "case-0"
    assert rows[0]["similarity"] == pytest.approx(1.0)

    all_rows = asyncio.run(store.fetch_candidates(_unit(0), "market_entry", ignore_domain=True))
    assert {r["case_id"] for r in all_rows} >= {"case-0", "case-6"}


def test_retriever_over_local_store_builds_reference_class(store_path: Path) -> None:
    retriever = Retriever(store=LocalCaseStore(store_path), embedder=FakeEmbedder())
    ref = asyncio.run(retriever.retrieve(_framed()))

    assert isinstance(ref, ReferenceClass)
    assert ref.base_rate.n == len(ref.cases)
    assert ref.cases[0].case_id == "case-0"
    counted = (
        ref.base_rate.success + ref.base_rate.mixed
        + ref.base_rate.failure + ref.base_rate.too_early
    )
    assert counted == ref.base_rate.n


def _critique(i: int) -> LensCritique:
    return LensCritique(
        lens_id=f"lens_{i}",
        lens_display_name=f"Lens {i}",
        verdict=LensVerdict.ENDORSES_WITH_CAVEATS,
        reasoning="Reasoning specific to the framed decision under test.",
        key_questions=["What is the downside if the assumption fails?"],
        most_relevant_case_ids=["case-0"],
        confidence="medium",
    )


def test_local_brief_store_round_trip(tmp_path: Path) -> None:
    briefs = LocalBriefStore(tmp_path / "briefs")
    case = RetrievedCase(
        case_id="case-0",
        title="Case 0",
        year=2000,
        organization="Org",
        decision_maker="CEO",
        domain=Domain.MARKET_ENTRY,
        decision_type=DecisionType.ONE_WAY,
        similarity=0.9,
        outcome_label=OutcomeLabel.SUCCESS,
        era_dependence=EraDependence.LOW,
        snippet="snippet",
    )
    brief = DecisionBrief(
        brief_id=str(uuid.uuid4()),
        framed_decision=_framed(),
        reference_class=ReferenceClass(
            cases=[case],
            base_rate=BaseRate(n=1, success=1, mixed=0, failure=0, too_early=0),
            weak_reference_class=True,
        ),
        lens_critiques=[_critique(i) for i in range(4)],
        tension_summary="The lenses mostly agreed; margin of safety dissented.",
        pre_mortem=["Capital runs out before traction.", "Incumbent price war."],
        cited_case_ids=["case-0"],
        calibration_notes=["reference class is small"],
    )
    asyncio.run(briefs.save(brief, "user input"))
    loaded = asyncio.run(briefs.get(brief.brief_id))
    assert loaded is not None
    assert loaded.brief_id == brief.brief_id
    assert len(loaded.lens_critiques) == 4
    assert asyncio.run(briefs.get("nonexistent-id")) is None
    assert asyncio.run(briefs.get("../evil")) is None
