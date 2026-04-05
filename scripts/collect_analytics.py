"""Inject demo analytics snapshots without running Browser Use.

This script creates a deterministic CHANEL post analytics storyline for the
scheduled checks `day_1`, `day_3`, and `week_1`, persists those snapshots to the
hackathon SQLite store, and exports a CSV with the full demo output.

Usage:
    uv run python scripts/collect_analytics.py
    uv run python scripts/collect_analytics.py --db-path data/demo.sqlite3
    uv run python scripts/collect_analytics.py --csv-path output/analytics_demo/demo.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hackathon_pipelines.contracts import PostAnalyticsSnapshot, PostedContentRecord
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore
from pydantic import BaseModel, ConfigDict

DEFAULT_DB_PATH = Path("data") / "hackathon_pipelines.sqlite3"
DEFAULT_CSV_PATH = Path("output") / "analytics_demo" / "chanel_post_analytics_demo.csv"
DEFAULT_RETENTION_CURVE_PCT = {
    "0": 100,
    "1": 88,
    "2": 76,
    "3": 68,
    "5": 52,
    "7": 41,
    "10": 30,
    "13": 22,
    "15": 18,
}


class DemoSnapshotSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_check: str
    days_after_post: int
    views: int
    likes: int
    comments: int
    shares: int
    saves: int
    follows_gained: int
    engagement_trend: str


class DemoAnalyticsScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_id: str
    post_url: str
    job_id: str
    caption: str
    product_name: str
    content_tier: str
    funnel_position: str
    target_niche: str
    analytics_check_intervals: list[str]
    posted_at: datetime
    retention_curve_pct: dict[str, int]
    retention_takeaway: str
    adaptation_recommendation: str
    snapshots: list[DemoSnapshotSpec]


class DemoAnalyticsCsvRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_id: str
    post_url: str
    product_name: str
    scheduled_check: str
    captured_at: datetime
    views: int
    likes: int
    comments: int
    shares: int
    saves: int
    follows_gained: int
    total_interactions: int
    engagement_rate_pct: float
    retention_0s_pct: int
    retention_1s_pct: int
    retention_2s_pct: int
    retention_3s_pct: int
    retention_5s_pct: int
    retention_7s_pct: int
    retention_10s_pct: int
    retention_13s_pct: int
    retention_15s_pct: int
    retention_curve_pct: str
    retention_takeaway: str
    adaptation_recommendation: str
    engagement_trend: str | None = None


class DemoAnalyticsRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db_path: str
    csv_path: str
    post_id: str
    post_url: str
    snapshot_ids: list[str]
    adaptation_recommendation: str


def _retention_pct(curve: dict[str, int], second: int) -> int:
    return int(curve[str(second)])


def _build_retention_takeaway(curve: dict[str, int]) -> str:
    first_second = _retention_pct(curve, 1)
    five_seconds = _retention_pct(curve, 5)
    return (
        f"Hook is strong at {first_second}% by 1 second, but mid-content retention falls "
        f"to {five_seconds}% by 5 seconds."
    )


def _build_adaptation_recommendation(curve: dict[str, int]) -> str:
    first_second = _retention_pct(curve, 1)
    five_seconds = _retention_pct(curve, 5)
    if first_second >= 85 and five_seconds <= 55:
        return "Keep the opening hook, then add a stronger pattern interrupt or payoff beat around seconds 3-5."
    return "Test a tighter opening and earlier payoff to reduce early drop-off."


def build_chanel_demo_scenario() -> DemoAnalyticsScenario:
    retention_curve_pct = dict(DEFAULT_RETENTION_CURVE_PCT)
    posted_at = datetime.now(UTC) - timedelta(days=7)
    return DemoAnalyticsScenario(
        post_id="CHANEL_DEMO_POST",
        post_url="https://www.instagram.com/reel/CHANEL_DEMO_POST/",
        job_id="job_chanel_demo_post",
        caption=(
            "day-to-night chanel styling with one hero bag, one beauty switch, and one luxe finishing touch."
        ),
        product_name="CHANEL post",
        content_tier="hero",
        funnel_position="consideration",
        target_niche="luxury beauty",
        analytics_check_intervals=["day_1", "day_3", "week_1"],
        posted_at=posted_at,
        retention_curve_pct=retention_curve_pct,
        retention_takeaway=_build_retention_takeaway(retention_curve_pct),
        adaptation_recommendation=_build_adaptation_recommendation(retention_curve_pct),
        snapshots=[
            DemoSnapshotSpec(
                scheduled_check="day_1",
                days_after_post=1,
                views=2_400,
                likes=180,
                comments=12,
                shares=8,
                saves=45,
                follows_gained=3,
                engagement_trend="launch_day_discovery",
            ),
            DemoSnapshotSpec(
                scheduled_check="day_3",
                days_after_post=3,
                views=8_900,
                likes=620,
                comments=38,
                shares=24,
                saves=156,
                follows_gained=12,
                engagement_trend="algorithm_pickup",
            ),
            DemoSnapshotSpec(
                scheduled_check="week_1",
                days_after_post=7,
                views=24_500,
                likes=1_800,
                comments=95,
                shares=67,
                saves=420,
                follows_gained=34,
                engagement_trend="sustained_compound_growth",
            ),
        ],
    )


def _upsert_posted_content(
    store: SQLiteHackathonStore, scenario: DemoAnalyticsScenario
) -> PostedContentRecord:
    existing = store.get_posted_content(scenario.post_url)
    record = PostedContentRecord(
        post_url=scenario.post_url,
        job_id=scenario.job_id,
        caption=scenario.caption,
        product_name=scenario.product_name,
        content_tier=scenario.content_tier,
        funnel_position=scenario.funnel_position,
        target_niche=scenario.target_niche,
        analytics_check_intervals=list(scenario.analytics_check_intervals),
        posted_at=scenario.posted_at,
    )
    if existing is not None:
        record = existing.model_copy(
            update={
                "caption": existing.caption or scenario.caption,
                "product_name": existing.product_name or scenario.product_name,
                "content_tier": existing.content_tier or scenario.content_tier,
                "funnel_position": existing.funnel_position or scenario.funnel_position,
                "target_niche": existing.target_niche or scenario.target_niche,
                "analytics_check_intervals": list(scenario.analytics_check_intervals),
            }
        )
    store.persist_posted_content(record)
    return record


def inject_demo_snapshots(
    store: SQLiteHackathonStore,
    scenario: DemoAnalyticsScenario,
) -> list[PostAnalyticsSnapshot]:
    _upsert_posted_content(store, scenario)
    snapshots: list[PostAnalyticsSnapshot] = []
    for spec in scenario.snapshots:
        snapshot = PostAnalyticsSnapshot(
            snapshot_id=f"snap_{scenario.post_id.lower()}_{spec.scheduled_check}",
            post_id=scenario.post_id,
            scheduled_check=spec.scheduled_check,
            views=spec.views,
            likes=spec.likes,
            comments=spec.comments,
            shares=spec.shares,
            saves=spec.saves,
            follows_gained=spec.follows_gained,
            retention_curve_pct=dict(scenario.retention_curve_pct),
            retention_takeaway=scenario.retention_takeaway,
            adaptation_recommendation=scenario.adaptation_recommendation,
            engagement_trend=spec.engagement_trend,
            captured_at=scenario.posted_at + timedelta(days=spec.days_after_post),
        )
        store.persist_post_analytics(snapshot)
        snapshots.append(snapshot)
    return snapshots


def _make_csv_row(
    *,
    scenario: DemoAnalyticsScenario,
    snapshot: PostAnalyticsSnapshot,
) -> DemoAnalyticsCsvRow:
    interactions = snapshot.likes + snapshot.comments + snapshot.shares + snapshot.saves
    engagement_rate_pct = round((interactions / snapshot.views) * 100, 2) if snapshot.views else 0.0
    curve = snapshot.retention_curve_pct
    return DemoAnalyticsCsvRow(
        post_id=scenario.post_id,
        post_url=scenario.post_url,
        product_name=scenario.product_name,
        scheduled_check=snapshot.scheduled_check or "",
        captured_at=snapshot.captured_at,
        views=snapshot.views,
        likes=snapshot.likes,
        comments=snapshot.comments,
        shares=snapshot.shares,
        saves=snapshot.saves,
        follows_gained=snapshot.follows_gained,
        total_interactions=interactions,
        engagement_rate_pct=engagement_rate_pct,
        retention_0s_pct=_retention_pct(curve, 0),
        retention_1s_pct=_retention_pct(curve, 1),
        retention_2s_pct=_retention_pct(curve, 2),
        retention_3s_pct=_retention_pct(curve, 3),
        retention_5s_pct=_retention_pct(curve, 5),
        retention_7s_pct=_retention_pct(curve, 7),
        retention_10s_pct=_retention_pct(curve, 10),
        retention_13s_pct=_retention_pct(curve, 13),
        retention_15s_pct=_retention_pct(curve, 15),
        retention_curve_pct=json.dumps(curve, separators=(",", ":"), sort_keys=True),
        retention_takeaway=snapshot.retention_takeaway or scenario.retention_takeaway,
        adaptation_recommendation=snapshot.adaptation_recommendation
        or scenario.adaptation_recommendation,
        engagement_trend=snapshot.engagement_trend,
    )


def export_demo_csv(
    *,
    scenario: DemoAnalyticsScenario,
    snapshots: list[PostAnalyticsSnapshot],
    csv_path: str | Path,
) -> Path:
    target_path = Path(csv_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_make_csv_row(scenario=scenario, snapshot=snapshot) for snapshot in snapshots]
    fieldnames = list(DemoAnalyticsCsvRow.model_fields.keys())
    with target_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump(mode="json"))
    return target_path.resolve()


def run_demo(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    csv_path: str | Path = DEFAULT_CSV_PATH,
) -> DemoAnalyticsRunResult:
    store = SQLiteHackathonStore(db_path=db_path)
    scenario = build_chanel_demo_scenario()
    snapshots = inject_demo_snapshots(store, scenario)
    resolved_csv_path = export_demo_csv(scenario=scenario, snapshots=snapshots, csv_path=csv_path)
    return DemoAnalyticsRunResult(
        db_path=str(Path(db_path).resolve()),
        csv_path=str(resolved_csv_path),
        post_id=scenario.post_id,
        post_url=scenario.post_url,
        snapshot_ids=[snapshot.snapshot_id for snapshot in snapshots],
        adaptation_recommendation=scenario.adaptation_recommendation,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inject deterministic demo analytics snapshots and export a CSV."
    )
    parser.add_argument(
        "--db-path", default=str(DEFAULT_DB_PATH), help="SQLite store path to update."
    )
    parser.add_argument(
        "--csv-path", default=str(DEFAULT_CSV_PATH), help="CSV export path for the demo analytics."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_demo(db_path=args.db_path, csv_path=args.csv_path)
    print(f"Injected analytics demo for {result.post_id} into {result.db_path}")
    print(f"Exported analytics CSV to {result.csv_path}")
    print(f"Adaptation recommendation: {result.adaptation_recommendation}")


if __name__ == "__main__":
    main()
