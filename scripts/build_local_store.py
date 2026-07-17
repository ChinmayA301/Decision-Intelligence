#!/usr/bin/env python3
"""
Build data/case_store.json — the zero-database case store.

Reads the YAML seed cases, validates them (same rules as load_cases.py),
computes embeddings, and writes a single JSON file the API can serve
retrieval from without Postgres.

Usage:
    python scripts/build_local_store.py [--dir data/seed_cases] [--out data/case_store.json]

Requires an embedding provider key (JINA_API_KEY by default; see
EMBEDDING_PROVIDER in .env). Run once; commit the output so the demo works
out of the box.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retriever.embeddings import get_embedder  # noqa: E402
from load_cases import validate_case, load_yaml  # noqa: E402

_STORE_FIELDS = (
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
    "option_taken",
    "review_status",
    "sources",
)


async def main(args: argparse.Namespace) -> None:
    cases_dir = Path(args.dir)
    yaml_files = sorted(cases_dir.glob("*.yaml"))
    if not yaml_files:
        print(f"No YAML files found in {cases_dir}", file=sys.stderr)
        sys.exit(1)

    embedder = get_embedder()
    cases: list[dict] = []
    skipped = 0

    for path in yaml_files:
        data = load_yaml(path)
        errors = validate_case(data, path)
        if errors:
            print(f"  SKIP {path.name}: {'; '.join(errors)}", file=sys.stderr)
            skipped += 1
            continue

        # Same embed text as the Postgres loader, so both stores rank alike.
        embed_text = f"{data['context_summary'].strip()} {data['option_taken'].strip()}"
        print(f"  Embedding {path.name}…", end=" ", flush=True)
        embedding = await embedder.embed_one(embed_text)
        print(f"dim={len(embedding)}")

        record = {k: data.get(k) for k in _STORE_FIELDS}
        record["context_summary"] = data["context_summary"].strip()
        record["year"] = int(data["year"])
        record["review_status"] = args.force_status or data.get("review_status", "draft")
        record["embedding"] = embedding
        cases.append(record)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"version": 1, "cases": cases}))
    reviewed = sum(1 for c in cases if c["review_status"] == "reviewed")
    print(f"\nWrote {out} — {len(cases)} cases ({reviewed} reviewed), {skipped} skipped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the local JSON case store")
    parser.add_argument("--dir", default="data/seed_cases")
    parser.add_argument("--out", default="data/case_store.json")
    parser.add_argument("--force-status", default=None, help="Override review_status for all cases")
    asyncio.run(main(parser.parse_args()))
