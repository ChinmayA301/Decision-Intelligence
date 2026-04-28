"""Unit tests for the Framer module against the 4 original test decisions."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.contracts import Domain, DecisionType, FramedDecision, FramerClarification  # noqa: E402
from src.framer.framer import Framer, _parse_response  # noqa: E402

_TEST_DECISIONS = yaml.safe_load(
    (Path(__file__).parent.parent / "evals" / "test_decisions.yaml").read_text()
)[:4]  # First 4 from original spec


# ─── Unit tests for _parse_response ──────────────────────────────────────────

def test_parse_response_framed_decision():
    raw = """
    {
        "type": "framed_decision",
        "data": {
            "choice_being_made": "Whether to switch to hybrid pricing",
            "alternatives": ["Keep current per-seat pricing", "Move to hybrid pricing"],
            "domain": "pricing",
            "decision_type": "sequential",
            "time_horizon_months": 18,
            "key_uncertainties": ["Impact on revenue predictability"],
            "constraints": ["$4M ARR"],
            "user_apparent_leaning": "toward change",
            "context_summary": "A B2B analytics company is deciding whether to change pricing."
        }
    }
    """
    result = _parse_response(raw)
    assert isinstance(result, FramedDecision)
    assert result.domain == Domain.PRICING
    assert result.decision_type == DecisionType.SEQUENTIAL
    assert len(result.alternatives) >= 2


def test_parse_response_clarification():
    raw = """
    {
        "type": "clarification",
        "data": {
            "reason": "No specific decision has been articulated.",
            "clarifying_questions": ["What specific decision are you weighing?"]
        }
    }
    """
    result = _parse_response(raw)
    assert isinstance(result, FramerClarification)
    assert len(result.clarifying_questions) >= 1


def test_parse_response_strips_markdown_fences():
    raw = """```json
    {
        "type": "clarification",
        "data": {
            "reason": "Too vague.",
            "clarifying_questions": ["What is the decision?"]
        }
    }
    ```"""
    result = _parse_response(raw)
    assert isinstance(result, FramerClarification)


def test_parse_response_invalid_json_raises():
    import json
    with pytest.raises(json.JSONDecodeError):
        _parse_response("not json at all")


def test_parse_response_distinct_alternatives_required():
    raw = """
    {
        "type": "framed_decision",
        "data": {
            "choice_being_made": "Test",
            "alternatives": ["Option A", "Option A"],
            "domain": "pricing",
            "decision_type": "reversible",
            "time_horizon_months": 12,
            "key_uncertainties": ["Something"],
            "constraints": [],
            "user_apparent_leaning": null,
            "context_summary": "Test context."
        }
    }
    """
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _parse_response(raw)


# ─── Integration tests against test decisions ─────────────────────────────────
# These require ANTHROPIC_API_KEY. Skip if not set.

pytestmark = pytest.mark.skipif(
    not __import__("os").environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)


@pytest.mark.asyncio
async def test_framer_test_p01_pricing():
    """test_p01: pricing decision should produce FramedDecision with domain=pricing."""
    spec = next(s for s in _TEST_DECISIONS if s["id"] == "test_p01")
    framer = Framer()
    result = await framer.frame(spec["user_input"])
    assert isinstance(result, FramedDecision), f"Expected FramedDecision, got {type(result)}"
    assert result.domain == Domain.PRICING
    assert len(result.alternatives) >= 2
    assert len(result.key_uncertainties) >= 1


@pytest.mark.asyncio
async def test_framer_test_m01_manda():
    """test_m01: M&A decision should produce FramedDecision with domain=m_and_a."""
    spec = next(s for s in _TEST_DECISIONS if s["id"] == "test_m01")
    framer = Framer()
    result = await framer.frame(spec["user_input"])
    assert isinstance(result, FramedDecision), f"Expected FramedDecision, got {type(result)}"
    assert result.domain == Domain.M_AND_A
    assert result.decision_type == DecisionType.ONE_WAY


@pytest.mark.asyncio
async def test_framer_test_p03_clarification():
    """test_p03: vague input must return FramerClarification."""
    spec = next(s for s in _TEST_DECISIONS if s["id"] == "test_p03")
    framer = Framer()
    result = await framer.frame(spec["user_input"])
    assert isinstance(result, FramerClarification), (
        f"Expected FramerClarification for vague input, got {type(result)}: {result}"
    )
    assert len(result.clarifying_questions) >= 1


@pytest.mark.asyncio
async def test_framer_test_me01_market_entry():
    """test_me01: market entry decision should frame correctly."""
    spec = next(s for s in _TEST_DECISIONS if s["id"] == "test_me01")
    framer = Framer()
    result = await framer.frame(spec["user_input"])
    assert isinstance(result, FramedDecision)
    assert result.domain == Domain.MARKET_ENTRY
    # Should capture the 9-month runway as a constraint
    all_text = " ".join(result.constraints + result.key_uncertainties).lower()
    assert "runway" in all_text or "9 month" in all_text
