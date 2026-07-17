"""Case store backends.

Two interchangeable backends feed the Retriever with candidate rows:

- ``PgCaseStore``    — Postgres + pgvector (production path, unchanged SQL).
- ``LocalCaseStore`` — a JSON file of cases with precomputed embeddings,
  cosine similarity computed in-process with numpy. With a ~30-case library
  this is exact (not approximate) and removes the Docker/Postgres requirement
  for local demos.

Both return plain mappings with the same keys the pgvector query yields, so
the Retriever's rerank / base-rate logic is backend-agnostic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import numpy as np

_TOP_K_INITIAL = 30

_ROW_KEYS = (
    "case_id",
    "title",
    "year",
    "organization",
    "decision_maker",
    "domain",
    "decision_type",
    "outcome_label",
    "era_dependence",
    "context_summary",
)


class CaseStore(Protocol):
    async def fetch_candidates(
        self, embedding: list[float], domain: str, ignore_domain: bool = False
    ) -> list[Any]: ...


class PgCaseStore:
    """pgvector-backed candidate fetch (the original SQL, verbatim)."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def fetch_candidates(
        self, embedding: list[float], domain: str, ignore_domain: bool = False
    ) -> list[Any]:
        vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"
        domain_clause = "" if ignore_domain else "AND domain = $2"
        params: list = [vec_literal]
        if not ignore_domain:
            params.append(domain)

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
            return await conn.fetch(query, *params)


class LocalCaseStore:
    """In-process candidate fetch over a JSON case file.

    The file is produced by ``scripts/build_local_store.py`` and contains the
    reviewed seed cases plus their embeddings. Cosine similarity over unit-
    normalized vectors matches pgvector's ``1 - (a <=> b)`` semantics.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        raw = json.loads(self._path.read_text())
        cases = [c for c in raw["cases"] if c.get("review_status") == "reviewed"]
        if not cases:
            raise ValueError(f"No reviewed cases in {self._path}")
        self._rows = [{k: c[k] for k in _ROW_KEYS} for c in cases]
        matrix = np.array([c["embedding"] for c in cases], dtype=np.float64)
        # Normalize once so retrieval is a single dot product.
        self._matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    def __len__(self) -> int:
        return len(self._rows)

    async def fetch_candidates(
        self, embedding: list[float], domain: str, ignore_domain: bool = False
    ) -> list[dict]:
        query = np.array(embedding, dtype=np.float64)
        query = query / np.linalg.norm(query)
        sims = self._matrix @ query

        candidates = [
            {**row, "similarity": float(sims[i])}
            for i, row in enumerate(self._rows)
            if ignore_domain or row["domain"] == domain
        ]
        candidates.sort(key=lambda r: r["similarity"], reverse=True)
        return candidates[:_TOP_K_INITIAL]
