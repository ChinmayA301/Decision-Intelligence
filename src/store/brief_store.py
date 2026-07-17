"""Brief persistence backends: Postgres (production) or local JSON files."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from src.contracts import DecisionBrief

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class BriefStore(Protocol):
    async def save(self, brief: DecisionBrief, user_input: str) -> None: ...
    async def get(self, brief_id: str) -> DecisionBrief | None: ...


class PgBriefStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def save(self, brief: DecisionBrief, user_input: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO briefs (brief_id, user_input, framed_decision, reference_class,
                                    lens_critiques, final_brief)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (brief_id) DO NOTHING
                """,
                brief.brief_id,
                user_input,
                brief.framed_decision.model_dump_json(),
                brief.reference_class.model_dump_json(),
                "[" + ",".join(c.model_dump_json() for c in brief.lens_critiques) + "]",
                brief.model_dump_json(),
            )

    async def get(self, brief_id: str) -> DecisionBrief | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT final_brief FROM briefs WHERE brief_id = $1", brief_id
            )
        if row is None:
            return None
        return DecisionBrief.model_validate_json(row["final_brief"])


class LocalBriefStore:
    """One JSON file per brief under a local directory (gitignored)."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, brief_id: str) -> Path:
        if not _SAFE_ID.match(brief_id):
            raise ValueError(f"Invalid brief_id: {brief_id!r}")
        return self._dir / f"{brief_id}.json"

    async def save(self, brief: DecisionBrief, user_input: str) -> None:
        payload = {
            "user_input": user_input,
            "final_brief": json.loads(brief.model_dump_json()),
        }
        self._path_for(brief.brief_id).write_text(json.dumps(payload, indent=2))

    async def get(self, brief_id: str) -> DecisionBrief | None:
        try:
            path = self._path_for(brief_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return DecisionBrief.model_validate(payload["final_brief"])
