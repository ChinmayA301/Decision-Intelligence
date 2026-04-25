#!/usr/bin/env python3
"""
Load YAML seed cases into Postgres and compute embeddings.

Usage:
    python scripts/load_cases.py [--dir data/seed_cases] [--status reviewed]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
import yaml
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retriever.embeddings import get_embedder
from src.retriever.retriever import create_pool

_REQUIRED_SOURCES = 2
_VALID_DOMAINS = {"pricing", "m_and_a", "market_entry", "key_hire", "product_sunset", "capital_allocation"}
_VALID_DECISION_TYPES = {"reversible", "one_way", "sequential"}
_VALID_OUTCOMES = {"success", "mixed", "failure", "too_early"}
_VALID_ERA = {"high", "medium", "low"}
_VALID_STATUS = {"draft", "reviewed", "published"}


def load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def validate_case(data: dict, path: Path) -> list[str]:
    errors: list[str] = []

    def check(condition: bool, msg: str):
        if not condition:
            errors.append(msg)

    check("case_id" in data, "missing case_id")
    check("title" in data, "missing title")
    check("decision_maker" in data, "missing decision_maker")
    check("organization" in data, "missing organization")
    check("year" in data, "missing year")
    check(data.get("domain") in _VALID_DOMAINS, f"invalid domain: {data.get('domain')!r}")
    check(data.get("decision_type") in _VALID_DECISION_TYPES, f"invalid decision_type: {data.get('decision_type')!r}")
    check("context_summary" in data, "missing context_summary")
    check(isinstance(data.get("options_considered"), list), "options_considered must be a list")
    check("option_taken" in data, "missing option_taken")
    check("outcome_12mo" in data, "missing outcome_12mo")
    check(data.get("outcome_label") in _VALID_OUTCOMES, f"invalid outcome_label: {data.get('outcome_label')!r}")
    check(data.get("era_dependence") in _VALID_ERA, f"invalid era_dependence: {data.get('era_dependence')!r}")
    check(data.get("review_status") in _VALID_STATUS, f"invalid review_status: {data.get('review_status')!r}")

    sources = data.get("sources", [])
    check(isinstance(sources, list), "sources must be a list")
    check(len(sources) >= _REQUIRED_SOURCES, f"need >= {_REQUIRED_SOURCES} sources, got {len(sources)}")

    return errors


async def upsert_case(
    conn: asyncpg.Connection,
    data: dict,
    embedding: list[float],
    force_status: str | None,
) -> str:
    case_id = data["case_id"]
    status = force_status or data.get("review_status", "draft")

    vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"

    await conn.execute(
        """
        INSERT INTO cases (
            case_id, title, decision_maker, organization, year,
            domain, decision_type, context_summary, options_considered,
            option_taken, stated_rationale, inferred_heuristics,
            constraints_at_time, outcome_12mo, outcome_36mo, outcome_label,
            counterfactual_signal, era_dependence, sources, embedding,
            review_status, reviewed_by
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9::jsonb,
            $10, $11, $12::jsonb,
            $13::jsonb, $14, $15, $16,
            $17, $18, $19::jsonb, $20::vector,
            $21, $22
        )
        ON CONFLICT (case_id) DO UPDATE SET
            title = EXCLUDED.title,
            decision_maker = EXCLUDED.decision_maker,
            organization = EXCLUDED.organization,
            year = EXCLUDED.year,
            domain = EXCLUDED.domain,
            decision_type = EXCLUDED.decision_type,
            context_summary = EXCLUDED.context_summary,
            options_considered = EXCLUDED.options_considered,
            option_taken = EXCLUDED.option_taken,
            stated_rationale = EXCLUDED.stated_rationale,
            inferred_heuristics = EXCLUDED.inferred_heuristics,
            constraints_at_time = EXCLUDED.constraints_at_time,
            outcome_12mo = EXCLUDED.outcome_12mo,
            outcome_36mo = EXCLUDED.outcome_36mo,
            outcome_label = EXCLUDED.outcome_label,
            counterfactual_signal = EXCLUDED.counterfactual_signal,
            era_dependence = EXCLUDED.era_dependence,
            sources = EXCLUDED.sources,
            embedding = EXCLUDED.embedding,
            review_status = EXCLUDED.review_status,
            reviewed_by = EXCLUDED.reviewed_by
        """,
        case_id,
        data["title"],
        data["decision_maker"],
        data["organization"],
        int(data["year"]),
        data["domain"],
        data["decision_type"],
        data["context_summary"].strip(),
        json.dumps(data.get("options_considered", [])),
        data["option_taken"],
        data.get("stated_rationale"),
        json.dumps(data.get("inferred_heuristics", [])),
        json.dumps(data.get("constraints_at_time", [])),
        data["outcome_12mo"],
        data.get("outcome_36mo"),
        data["outcome_label"],
        data.get("counterfactual_signal"),
        data["era_dependence"],
        json.dumps(data.get("sources", [])),
        vec_literal,
        status,
        data.get("reviewed_by"),
    )
    return case_id


async def main(args: argparse.Namespace) -> None:
    cases_dir = Path(args.dir)
    yaml_files = sorted(cases_dir.glob("*.yaml"))

    if not yaml_files:
        print(f"No YAML files found in {cases_dir}", file=sys.stderr)
        sys.exit(1)

    embedder = get_embedder()
    pool = await create_pool()

    loaded = 0
    skipped = 0
    errors_total = 0

    async with pool.acquire() as conn:
        for path in yaml_files:
            try:
                data = load_yaml(path)
            except yaml.YAMLError as exc:
                print(f"  YAML parse error in {path.name}: {exc}", file=sys.stderr)
                errors_total += 1
                continue

            errors = validate_case(data, path)
            if errors:
                print(f"  SKIP {path.name}: {'; '.join(errors)}", file=sys.stderr)
                skipped += 1
                continue

            if args.status_filter and data.get("review_status") not in args.status_filter.split(","):
                print(f"  SKIP {path.name}: status={data.get('review_status')!r} (filtered)")
                skipped += 1
                continue

            # Compute embedding over context_summary + option_taken
            embed_text = f"{data['context_summary'].strip()} {data['option_taken'].strip()}"
            print(f"  Embedding {path.name}…", end=" ", flush=True)
            embedding = await embedder.embed_one(embed_text)
            print(f"dim={len(embedding)}")

            case_id = await upsert_case(conn, data, embedding, args.force_status)
            print(f"  OK {case_id}")
            loaded += 1

    await pool.close()
    print(f"\nDone: {loaded} loaded, {skipped} skipped, {errors_total} errors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load seed cases into Postgres")
    parser.add_argument("--dir", default="data/seed_cases", help="Directory of YAML case files")
    parser.add_argument("--force-status", default=None, help="Override review_status for all cases")
    parser.add_argument("--status-filter", default=None, help="Only load cases with this status (comma-sep)")
    asyncio.run(main(parser.parse_args()))
