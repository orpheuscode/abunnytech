"""
Metrics ingestion interfaces and fixture-driven mock implementation.

AbstractMetricsIngester defines what Stage 4 expects from any data source.
MockMetricsIngester loads from JSON fixture files — no credentials needed.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import DistributionRecord, PerformanceMetricRecord


class AbstractMetricsIngester(ABC):
    """
    Interface between Stage 4 and any analytics data source.

    Implementations:
        MockMetricsIngester      — loads from fixture JSON, no credentials
        PlatformAPIIngester      — calls live platform APIs via browser_runtime
        BrowserExtractIngester   — scrapes analytics dashboards via browser_runtime
    """

    @abstractmethod
    async def fetch_post_metrics(
        self,
        distribution_record: DistributionRecord,
    ) -> PerformanceMetricRecord | None:
        """
        Fetch analytics for a single distributed post.
        Returns None if the post is too new or data is unavailable.
        """

    @abstractmethod
    async def fetch_account_metrics(
        self,
        platform: str,
        account_id: str,
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        """
        Fetch account-level aggregate metrics (follower count, reach, etc.).
        Returns raw dicts — callers normalise as needed.
        """

    @abstractmethod
    async def batch_fetch(
        self,
        distribution_records: list[DistributionRecord],
    ) -> list[PerformanceMetricRecord]:
        """
        Bulk-fetch metrics for a list of distribution records.
        Skips records with no post_id.
        """


class MockMetricsIngester(AbstractMetricsIngester):
    """
    Fixture-driven ingester for tests and dry-run demos.

    On first call it loads a JSON fixture whose top-level key is "posts",
    keyed by post_id. Unrecognised post_ids return plausible synthetic data
    seeded from the distribution_record fields.
    """

    def __init__(self, fixture_path: str | None = None) -> None:
        self._fixture_path = Path(fixture_path) if fixture_path else None
        self._store: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if self._fixture_path and self._fixture_path.exists():
            raw = json.loads(self._fixture_path.read_text(encoding="utf-8"))
            self._store = {item["post_id"]: item for item in raw.get("posts", [])}
        self._loaded = True

    def _synthetic(self, record: DistributionRecord) -> dict[str, Any]:
        """Generate deterministic synthetic metrics from the record's fields."""
        import hashlib
        seed = int(hashlib.md5(record.record_id.encode()).hexdigest()[:8], 16)
        views = 1000 + (seed % 50_000)
        likes = int(views * (0.02 + (seed % 100) / 2000))
        comments = max(1, likes // 10)
        shares = max(0, likes // 20)
        saves = max(0, likes // 5)
        completion = 20.0 + (seed % 60)
        hook_3s = 40.0 + (seed % 50)
        eng_rate = round((likes + comments + shares + saves) / views * 100, 2)
        return {
            "post_id": record.post_id or record.record_id,
            "views": views,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "saves": saves,
            "follows_gained": max(0, likes // 50),
            "watch_time_avg_seconds": round(completion * 0.3, 1),
            "completion_rate_pct": round(completion, 1),
            "hook_retention_3s_pct": round(hook_3s, 1),
            "hook_retention_50pct": round(hook_3s * 0.6, 1),
            "engagement_rate_pct": eng_rate,
            "revenue_attributed": round((seed % 50) * 0.75, 2),
        }

    async def fetch_post_metrics(
        self,
        distribution_record: DistributionRecord,
    ) -> PerformanceMetricRecord | None:
        if not distribution_record.post_id:
            return None
        self._load()
        raw = self._store.get(distribution_record.post_id) or self._synthetic(distribution_record)
        return PerformanceMetricRecord(
            distribution_record_id=distribution_record.record_id,
            post_id=distribution_record.post_id,
            platform=distribution_record.platform,
            content_package_id=distribution_record.content_package_id,
            video_blueprint_id=distribution_record.video_blueprint_id,
            audio_id=raw.get("audio_id") or distribution_record.audio_id,
            schedule_slot=raw.get("schedule_slot") or distribution_record.schedule_slot,
            content_tier=raw.get("content_tier"),
            hook_style=raw.get("hook_style"),
            product_id=raw.get("product_id"),
            views=raw["views"],
            likes=raw["likes"],
            comments=raw["comments"],
            shares=raw["shares"],
            saves=raw["saves"],
            follows_gained=raw["follows_gained"],
            watch_time_avg_seconds=raw["watch_time_avg_seconds"],
            completion_rate_pct=raw["completion_rate_pct"],
            hook_retention_3s_pct=raw["hook_retention_3s_pct"],
            hook_retention_50pct=raw["hook_retention_50pct"],
            engagement_rate_pct=raw["engagement_rate_pct"],
            revenue_attributed=raw["revenue_attributed"],
            source="mock",
        )

    async def fetch_account_metrics(
        self,
        platform: str,
        account_id: str,
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        return [
            {
                "platform": platform,
                "account_id": account_id,
                "since": since.isoformat(),
                "until": until.isoformat(),
                "follower_count": 12_450,
                "follower_growth": 312,
                "total_reach": 285_000,
                "profile_visits": 4_200,
                "source": "mock",
            }
        ]

    async def batch_fetch(
        self,
        distribution_records: list[DistributionRecord],
    ) -> list[PerformanceMetricRecord]:
        results: list[PerformanceMetricRecord] = []
        for record in distribution_records:
            metric = await self.fetch_post_metrics(record)
            if metric:
                results.append(metric)
        return results

