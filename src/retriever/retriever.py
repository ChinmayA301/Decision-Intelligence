"""Retriever — embeds a FramedDecision and fetches analogous cases from a CaseStore
(Postgres/pgvector in production, or a local JSON store for zero-dependency demos)."""
from __future__ import annotations

import os

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
from src.store.case_store import CaseStore

_TOP_K_FINAL = 10
_WEAK_CLASS_THRESHOLD = 4


class Retriever:
    def __init__(
        self,
        store: CaseStore,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._store = store
        # Built on first use rather than at construction: a missing embedding key
        # should surface as a clear error on the request that needs it, not as a
        # crash during app startup (which turns into a health-check crash loop on
        # hosted platforms and hides the reason).
        self._embedder = embedder
        self._embedder_error: Exception | None = None

    @property
    def embedder(self) -> EmbeddingProvider:
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    def embedder_ready(self) -> bool:
        """Whether embeddings are usable, for diagnostics. Never raises."""
        try:
            _ = self.embedder
            return True
        except Exception:  # noqa: BLE001 - reported, not raised
            return False

    async def retrieve(self, decision: FramedDecision) -> ReferenceClass:
        embed_text = f"{decision.context_summary} {decision.choice_being_made}"
        embedding = await self.embedder.embed_one(embed_text)

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
    ) -> list:
        rows = await self._store.fetch_candidates(
            embedding, decision.domain.value, ignore_domain=ignore_domain
        )
        return _rerank(rows, decision)


def _rerank(rows: list, decision: FramedDecision) -> list:
    """Re-rank: boost decision_type match; penalize high era_dependence.

    Rows may be asyncpg Records or plain dicts; both support key access."""
    def score(row) -> float:
        sim: float = row["similarity"]
        boost = 0.0
        if row["decision_type"] == decision.decision_type.value:
            boost += 0.05
        if row["era_dependence"] == EraDependence.HIGH.value:
            boost -= 0.08
        return sim + boost

    return sorted(rows, key=score, reverse=True)


def _row_to_retrieved_case(row) -> RetrievedCase:
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


async def create_pool(dsn: str | None = None):
    """Postgres connection pool. asyncpg is imported here rather than at module
    scope so the local-store path — and serverless bundles built for it — do not
    need the driver installed at all."""
    import asyncpg

    return await asyncpg.create_pool(dsn or os.environ["DATABASE_URL"])
