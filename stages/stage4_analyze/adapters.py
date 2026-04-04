from __future__ import annotations

from typing import Protocol

import structlog

from packages.contracts.analytics import (
    MetricType,
    OptimizationAction,
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
)
from packages.contracts.base import Platform

logger = structlog.get_logger(__name__)


class MetricsCollectorAdapter(Protocol):
    async def collect(
        self, distribution_record_id: str, platform: Platform
    ) -> list[PerformanceMetricRecord]:
        """Fetch performance metrics for a single distribution (post) record."""
        ...


class PerformanceAnalyzerAdapter(Protocol):
    async def analyze(self, metrics: list[PerformanceMetricRecord]) -> OptimizationDirectiveEnvelope:
        """Turn raw metrics into optimization directives."""
        ...


class MockMetricsCollector:
    """Returns plausible social stats (~1.2K views, double-digit likes, ~3% engagement)."""

    def __init__(self, *, default_identity_id: str = "demo-creator") -> None:
        self._default_identity_id = default_identity_id

    async def collect(
        self, distribution_record_id: str, platform: Platform
    ) -> list[PerformanceMetricRecord]:
        logger.debug(
            "mock_metrics_collect",
            distribution_record_id=distribution_record_id,
            platform=platform.value,
        )
        post_age_hours = 18.5
        identity_id = self._default_identity_id
        return [
            PerformanceMetricRecord(
                distribution_record_id=distribution_record_id,
                identity_id=identity_id,
                platform=platform,
                metric_type=MetricType.VIEWS,
                value=1247.0,
                post_age_hours=post_age_hours,
            ),
            PerformanceMetricRecord(
                distribution_record_id=distribution_record_id,
                identity_id=identity_id,
                platform=platform,
                metric_type=MetricType.LIKES,
                value=45.0,
                post_age_hours=post_age_hours,
            ),
            PerformanceMetricRecord(
                distribution_record_id=distribution_record_id,
                identity_id=identity_id,
                platform=platform,
                metric_type=MetricType.COMMENTS,
                value=12.0,
                post_age_hours=post_age_hours,
            ),
            PerformanceMetricRecord(
                distribution_record_id=distribution_record_id,
                identity_id=identity_id,
                platform=platform,
                metric_type=MetricType.SHARES,
                value=18.0,
                post_age_hours=post_age_hours,
            ),
            PerformanceMetricRecord(
                distribution_record_id=distribution_record_id,
                identity_id=identity_id,
                platform=platform,
                metric_type=MetricType.ENGAGEMENT_RATE,
                value=3.2,
                post_age_hours=post_age_hours,
            ),
            PerformanceMetricRecord(
                distribution_record_id=distribution_record_id,
                identity_id=identity_id,
                platform=platform,
                metric_type=MetricType.CLICK_THROUGH,
                value=2.1,
                post_age_hours=post_age_hours,
            ),
            PerformanceMetricRecord(
                distribution_record_id=distribution_record_id,
                identity_id=identity_id,
                platform=platform,
                metric_type=MetricType.WATCH_TIME,
                value=42.0,
                post_age_hours=post_age_hours,
            ),
        ]


class MockPerformanceAnalyzer:
    async def analyze(self, metrics: list[PerformanceMetricRecord]) -> OptimizationDirectiveEnvelope:
        identity_id = metrics[0].identity_id if metrics else "unknown"
        window = 24.0
        if metrics:
            ages = [m.post_age_hours for m in metrics if m.post_age_hours > 0]
            if ages:
                window = max(ages)

        directives = [
            OptimizationAction(
                target_stage=1,
                action_type="refresh_trend_scan",
                parameters={"lookback_hours": 48, "niche_weight": 0.35},
                reason="Mock: engagement_rate steady but views plateauing — check rising formats",
                priority=2,
            ),
            OptimizationAction(
                target_stage=2,
                action_type="tighten_hook",
                parameters={"first_frame_seconds": 1.2, "caption_cta": True},
                reason="Mock: improve scroll-stopping open based on watch_time / views ratio",
                priority=1,
            ),
        ]

        return OptimizationDirectiveEnvelope(
            identity_id=identity_id,
            analysis_window_hours=window,
            directives=directives,
            summary=(
                "Mock analysis: content is reaching ~1.2K views with healthy likes and ~3.2% "
                "engagement; next wins likely from hook refresh and trend realignment."
            ),
            confidence=0.78,
        )
