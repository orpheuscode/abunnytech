"""
pytest fixtures for Stage 4 tests.

All fixtures use in-memory state (tmp_path SQLite, fixture JSON) so tests
run without network access or credentials.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.stage4_analytics.contracts import DistributionRecord, PerformanceMetricRecord
from agents.stage4_analytics.ingestion import MockMetricsIngester
from agents.stage4_analytics.state_adapter import StateAdapter

FIXTURE_DIR = Path(__file__).parent / "fixtures"
ANALYTICS_FIXTURE = FIXTURE_DIR / "sample_analytics.json"
RETENTION_FIXTURE = FIXTURE_DIR / "fixtures" / "sample_retention.json"


@pytest.fixture
def fixture_metrics() -> list[PerformanceMetricRecord]:
    """Load the 10-post fixture dataset as PerformanceMetricRecord objects."""
    raw = json.loads(ANALYTICS_FIXTURE.read_text(encoding="utf-8"))
    records = []
    for i, post in enumerate(raw["posts"]):
        records.append(
            PerformanceMetricRecord(
                distribution_record_id=f"dist_{i:03d}",
                post_id=post["post_id"],
                platform=post["platform"],
                content_package_id=f"pkg_{i:03d}",
                video_blueprint_id=f"bp_{i:03d}",
                hook_style=post.get("hook_style"),
                content_tier=post.get("content_tier"),
                audio_id=post.get("audio_id"),
                schedule_slot=post.get("schedule_slot"),
                product_id=post.get("product_id"),
                views=post["views"],
                likes=post["likes"],
                comments=post["comments"],
                shares=post["shares"],
                saves=post["saves"],
                follows_gained=post["follows_gained"],
                watch_time_avg_seconds=post["watch_time_avg_seconds"],
                completion_rate_pct=post["completion_rate_pct"],
                hook_retention_3s_pct=post["hook_retention_3s_pct"],
                hook_retention_50pct=post["hook_retention_50pct"],
                engagement_rate_pct=post["engagement_rate_pct"],
                revenue_attributed=post["revenue_attributed"],
                source="mock",
            )
        )
    return records


@pytest.fixture
def distribution_records() -> list[DistributionRecord]:
    """Distribution records matching the fixture analytics."""
    raw = json.loads(ANALYTICS_FIXTURE.read_text(encoding="utf-8"))
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


@pytest.fixture
def tmp_adapter(tmp_path: Path) -> StateAdapter:
    """SQLite adapter backed by a temporary test directory."""
    return StateAdapter(db_path=str(tmp_path / "test_stage4.db"))


@pytest.fixture
def mock_ingester() -> MockMetricsIngester:
    return MockMetricsIngester(fixture_path=str(ANALYTICS_FIXTURE))
