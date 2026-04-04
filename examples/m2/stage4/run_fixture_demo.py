"""
Stage 4 end-to-end fixture demo.

Runs the full analysis pipeline on the sample_analytics.json fixture
and prints a daily summary, directives, and redo queue to stdout.

Usage:
    cd abunnytech
    python examples/stage4/run_fixture_demo.py

    # With non-default DB path:
    STAGE4_DB=./tmp/demo.db python examples/stage4/run_fixture_demo.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.stage4_analytics.contracts import DistributionRecord
from agents.stage4_analytics.runner import Stage4Runner

FIXTURE_PATH = Path(__file__).parent.parent.parent / "tests/stage4/fixtures/sample_analytics.json"
DB_PATH = os.environ.get("STAGE4_DB", "./data/stage4_demo.db")


def _load_distribution_records() -> list[DistributionRecord]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [
        DistributionRecord(
            record_id=f"dist_{i:03d}",
            content_package_id=f"pkg_{i:03d}",
            video_blueprint_id=f"bp_{i:03d}",
            platform=post["platform"],
            post_id=post["post_id"],
            status="posted",
            audio_id=post.get("audio_id"),
            schedule_slot=post.get("schedule_slot"),
        )
        for i, post in enumerate(raw["posts"])
    ]


async def main() -> None:
    print("=" * 72)
    print("  Stage 4 - Analyze & Adapt  [DRY RUN / FIXTURE MODE]")
    print("=" * 72)
    print(f"  Fixture: {FIXTURE_PATH.name}")
    print(f"  DB:      {DB_PATH}")
    print()

    distribution_records = _load_distribution_records()
    print(f"Loaded {len(distribution_records)} distribution records from fixture.\n")

    runner = Stage4Runner(
        dry_run=True,
        db_path=DB_PATH,
        fixture_path=str(FIXTURE_PATH),
        niche="beauty",
    )
    result = await runner.run_weekly(distribution_records)

    print("-" * 72)
    print(f"  Metrics ingested:  {len(result.metrics)}")
    print(f"  Directives issued: {len(result.directives)}")
    print(f"  Redo queue items:  {len(result.redo_items)}")
    print("-" * 72)
    print()

    print("### DIRECTIVES ###")
    for d in result.directives:
        print(f"  [{d.priority.upper():8s}] {d.directive_type:30s} -> {d.target_stage}")
        print(f"           {d.rationale[:100]}")
        print()

    print("### REDO QUEUE ###")
    for item in result.redo_items:
        print(f"  [{item.priority.upper():8s}] {item.redo_reason:20s} -> {item.target_stage}")
        mutations = ", ".join(f"{k}={v}" for k, v in item.suggested_mutations.items())
        print(f"           mutations: {mutations}")
        print()

    print("-" * 72)
    print(result.summary_daily)
    print("-" * 72)
    if result.summary_weekly:
        print(result.summary_weekly)

    print("\nDemo complete. State persisted to:", DB_PATH)


if __name__ == "__main__":
    asyncio.run(main())
