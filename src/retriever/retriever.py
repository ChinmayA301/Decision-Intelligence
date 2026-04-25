"""Retriever — embeds a FramedDecision and fetches analogous cases from Postgres/pgvector."""
from __future__ import annotations

import os

import asyncpg

from src.contracts import (
    BaseRate,
    Domain,
    DecisionType,
    EraDependence,
    FramedDecision,
    OutcomeLabel,
    ReferenceClass,
    RetrievedCase,
)
from src.retriever.embeddings import EmbeddingProvider, get_embedder

_TOP_K_INITIAL = 30
_TOP_K_FINAL = 10
_WEAK_CLASS_THRESHOLD = 4


class Retriever:
    def __init__(
        self,
        pool: asyncpg.Pool,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._pool = pool
        self._embedder = embedder or get_embedder()

    async def retrieve(self, decision: FramedDecision) -> ReferenceClass:
        embed_text = f"{decision.context_summary} {decision.choice_being_made}"
        embedding = await self._embedder.embed_one(embed_text)

        rows = await self._fetch_candidates(embedding, decision)
        cases = [_row_to_retrieved_case(r) for r in rows]

        if len(cases) < _WEAK_CLASS_THRESHOLD:
            # Fallback: broaden to any domain
            rows = await self._fetch_candidates(embedding, decision, ignore_domain=True)
            cases = [_row_to_retrieved_case(r) for r in rows]

        cases = cases[:_TOP_K_FINAL]

        base_rate = _compute_base_rate(cases)
        weak = len(cases) < _WEAK_CLASS_THRESHOLD

        return ReferenceClass(cases=cases, base_rate=base_rate, weak_reference_class=weak)

    async def _fetch_candidates(
        self,
        embedding: list[float],
        decision: FramedDecision,
        ignore_domain: bool = False,
    ) -> list[asyncpg.Record]:
        vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"

        # Build query with optional domain filter
        domain_clause = "" if ignore_domain else "AND domain = $2"
        params: list = [vec_literal]
        if not ignore_domain:
            params.append(decision.domain.value)

        query = f"""
            SELECT
                case_id,
                title,
                year,
                organization,
                decision_maker,
                domain,
                decision_type,
                outcome_label,
                era_dependence,
                context_summary,
                1 - (embedding <=> $1::vector) AS similarity
            FROM cases
            WHERE review_status = 'reviewed'
              AND embedding IS NOT NULL
              {domain_clause}
            ORDER BY embedding <=> $1::vector
            LIMIT {_TOP_K_INITIAL}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return _rerank(rows, decision)


def _rerank(rows: list[asyncpg.Record], decision: FramedDecision) -> list[asyncpg.Record]:
    """Re-rank: boost decision_type match; penalize high era_dependence."""
    def score(row: asyncpg.Record) -> float:
        sim: float = row["similarity"]
        boost = 0.0
        if row["decision_type"] == decision.decision_type.value:
            boost += 0.05
        if row["era_dependence"] == EraDependence.HIGH.value:
            boost -= 0.08
        return sim + boost

    return sorted(rows, key=score, reverse=True)


def _row_to_retrieved_case(row: asyncpg.Record) -> RetrievedCase:
    context = row["context_summary"] or ""
    snippet = context[:800].rsplit(" ", 1)[0] + "…" if len(context) > 800 else context
    return RetrievedCase(
        case_id=row["case_id"],
        title=row["title"],
        year=row["year"],
        organization=row["organization"],
        decision_maker=row["decision_maker"],
        domain=Domain(row["domain"]),
        decision_type=DecisionType(row["decision_type"]),
        similarity=max(0.0, min(1.0, float(row["similarity"]))),
        outcome_label=OutcomeLabel(row["outcome_label"]),
        era_dependence=EraDependence(row["era_dependence"]),
        snippet=snippet,
    )


def _compute_base_rate(cases: list[RetrievedCase]) -> BaseRate:
    counts = {label: 0 for label in OutcomeLabel}
    for c in cases:
        counts[c.outcome_label] += 1
    return BaseRate(
        n=len(cases),
        success=counts[OutcomeLabel.SUCCESS],
        mixed=counts[OutcomeLabel.MIXED],
        failure=counts[OutcomeLabel.FAILURE],
        too_early=counts[OutcomeLabel.TOO_EARLY],
    )


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn or os.environ["DATABASE_URL"])
