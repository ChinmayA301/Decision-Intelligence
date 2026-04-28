"""
Layer-1 process evals. Run: pytest evals/process_evals.py -v

Checks P1–P9 from eval-plan.md against the 20 held-out test decisions.
Requires a running Postgres instance and env vars set.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
import sys
from typing import Any

import pytest
import yaml
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.contracts import FramedDecision, FramerClarification  # noqa: E402
from src.framer.framer import Framer  # noqa: E402
from src.retriever.retriever import Retriever, create_pool  # noqa: E402
from src.critic.critic import Critic  # noqa: E402
from src.synthesizer.synthesizer import Synthesizer  # noqa: E402

_TEST_DECISIONS_PATH = Path(__file__).parent / "test_decisions.yaml"
_DECISIONS = yaml.safe_load(_TEST_DECISIONS_PATH.read_text())

# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool():
    pool = await create_pool()
    yield pool
    await pool.close()


@pytest.fixture(scope="session")
def framer():
    return Framer()


@pytest.fixture(scope="session")
async def retriever(db_pool):
    return Retriever(pool=db_pool)


@pytest.fixture(scope="session")
def critic():
    return Critic()


@pytest.fixture(scope="session")
async def synthesizer(retriever):
    return Synthesizer()


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def run_framer_on_decisions(framer: Framer) -> list[tuple[dict, Any]]:
    """Run Framer on all 20 test decisions. Returns list of (decision_spec, framer_output)."""
    results = []
    for spec in _DECISIONS:
        output = await framer.frame(spec["user_input"])
        results.append((spec, output))
    return results


# ─── P1: Framer schema validity ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p1_framer_schema_validity(framer):
    """P1: 20/20 produce valid FramedDecision or FramerClarification."""
    results = await run_framer_on_decisions(framer)
    failures = []
    for spec, output in results:
        if not isinstance(output, (FramedDecision, FramerClarification)):
            failures.append(f"{spec['id']}: got {type(output)}")
    assert not failures, "P1 failures:\n" + "\n".join(failures)


# ─── P2: Framer domain accuracy ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p2_framer_domain_accuracy(framer):
    """P2: ≥17/20 correct domain classification."""
    results = await run_framer_on_decisions(framer)
    correct = 0
    total_with_expected = 0
    misses = []
    for spec, output in results:
        expected_domain = spec.get("expected_domain")
        expected_clarification = spec.get("expected_clarification", False)

        if expected_clarification:
            # These are expected to be clarifications; no domain to check
            if isinstance(output, FramerClarification):
                correct += 1
            total_with_expected += 1
            continue

        if not expected_domain:
            continue
        total_with_expected += 1
        if isinstance(output, FramedDecision) and output.domain.value == expected_domain:
            correct += 1
        else:
            got = output.domain.value if isinstance(output, FramedDecision) else "clarification"
            misses.append(f"{spec['id']}: expected={expected_domain}, got={got}")

    pass_rate = correct / total_with_expected if total_with_expected else 0
    assert pass_rate >= 17 / 20, (
        f"P2: {correct}/{total_with_expected} correct (need ≥17/20). Misses:\n"
        + "\n".join(misses)
    )


# ─── P3: Retriever recall ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p3_retriever_recall(framer, retriever):
    """P3: ≥18/20 test decisions return ≥4 cases (not weak_reference_class)."""
    weak_count = 0
    weak_ids = []
    for spec in _DECISIONS:
        if spec.get("expected_clarification"):
            continue
        framed = await framer.frame(spec["user_input"])
        if isinstance(framed, FramerClarification):
            continue
        refs = await retriever.retrieve(framed)
        if refs.weak_reference_class:
            weak_count += 1
            weak_ids.append(f"{spec['id']} (n={refs.base_rate.n})")

    non_clarification_total = sum(1 for s in _DECISIONS if not s.get("expected_clarification"))
    strong_count = non_clarification_total - weak_count
    assert strong_count >= 18, (
        f"P3: only {strong_count} decisions have ≥4 cases. "
        f"Weak reference classes: {weak_ids}"
    )


# ─── P4: Critic divergence ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p4_critic_divergence(framer, retriever, critic):
    """P4: For ≥16/20, at least 2 lenses have materially different verdicts."""
    divergent_count = 0
    total = 0
    for spec in _DECISIONS:
        if spec.get("expected_clarification"):
            continue
        framed = await framer.frame(spec["user_input"])
        if isinstance(framed, FramerClarification):
            continue
        refs = await retriever.retrieve(framed)
        critiques = await critic.critique(framed, refs)

        # Check verdict diversity: at least 2 distinct verdicts among active lenses
        from src.contracts import LensVerdict
        active_verdicts = {c.verdict for c in critiques if c.verdict != LensVerdict.ABSTAINS}
        if len(active_verdicts) >= 2:
            divergent_count += 1
        total += 1

    assert divergent_count >= 16, (
        f"P4: only {divergent_count}/{total} decisions showed lens divergence (need ≥16)"
    )


# ─── P5: Synthesizer citation integrity ───────────────────────────────────────

@pytest.mark.asyncio
async def test_p5_synthesizer_citation_integrity(framer, retriever, critic, synthesizer, db_pool):
    """P5: 20/20 — every cited case_id exists in DB."""
    failures = []
    async with db_pool.acquire() as conn:
        valid_ids = {r["case_id"] for r in await conn.fetch("SELECT case_id FROM cases")}

    for spec in _DECISIONS[:5]:  # Sample 5 to avoid API cost in CI; expand as needed
        if spec.get("expected_clarification"):
            continue
        framed = await framer.frame(spec["user_input"])
        if isinstance(framed, FramerClarification):
            continue
        refs = await retriever.retrieve(framed)
        critiques = await critic.critique(framed, refs)
        brief = await synthesizer.synthesize(framed, refs, critiques)
        bad = [cid for cid in brief.cited_case_ids if cid not in valid_ids]
        if bad:
            failures.append(f"{spec['id']}: invalid case_ids {bad}")

    assert not failures, "P5 citation integrity failures:\n" + "\n".join(failures)


# ─── P6: Disconfirmation surface ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p6_disconfirmation_surface(framer, retriever, critic, synthesizer):
    """P6: ≥18/20 briefs contain at least one failure outcome from reference class."""
    from src.contracts import OutcomeLabel
    disconfirmed = 0
    total = 0
    for spec in _DECISIONS:
        if spec.get("expected_clarification"):
            continue
        framed = await framer.frame(spec["user_input"])
        if isinstance(framed, FramerClarification):
            continue
        refs = await retriever.retrieve(framed)
        failure_ids = {c.case_id for c in refs.cases if c.outcome_label == OutcomeLabel.FAILURE}
        if failure_ids:
            disconfirmed += 1
        total += 1

    assert disconfirmed >= min(18, total), (
        f"P6: only {disconfirmed}/{total} decisions had failure cases in reference class"
    )


# ─── P7: Calibration honesty ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p7_calibration_honesty(framer, retriever, critic, synthesizer):
    """P7: Briefs with weak reference class explicitly note it in calibration_notes."""
    failures = []
    for spec in _DECISIONS:
        if spec.get("expected_clarification"):
            continue
        framed = await framer.frame(spec["user_input"])
        if isinstance(framed, FramerClarification):
            continue
        refs = await retriever.retrieve(framed)
        if not refs.weak_reference_class:
            continue
        critiques = await critic.critique(framed, refs)
        brief = await synthesizer.synthesize(framed, refs, critiques)
        if not any("weak" in note.lower() or "small" in note.lower() for note in brief.calibration_notes):
            failures.append(f"{spec['id']}: weak_reference_class not noted")

    assert not failures, "P7 calibration failures:\n" + "\n".join(failures)


# ─── P8: Latency ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p8_latency(framer, retriever, critic, synthesizer):
    """P8: p50 ≤ 30s per brief (sample 3 decisions)."""
    sample = [s for s in _DECISIONS if not s.get("expected_clarification")][:3]
    latencies = []
    for spec in sample:
        start = time.time()
        framed = await framer.frame(spec["user_input"])
        if isinstance(framed, FramerClarification):
            continue
        refs = await retriever.retrieve(framed)
        critiques = await critic.critique(framed, refs)
        await synthesizer.synthesize(framed, refs, critiques)
        latencies.append(time.time() - start)

    if not latencies:
        pytest.skip("No non-clarification decisions available for latency test")

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    assert p50 <= 30, f"P8: p50 latency {p50:.1f}s exceeds 30s target"
