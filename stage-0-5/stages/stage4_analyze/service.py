from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import select

from packages.contracts.analytics import (
    MetricType,
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    RedoQueueItem,
    RedoReason,
)
from packages.contracts.base import Platform, utc_now
from packages.shared.db import PipelineRecord, get_async_session, log_audit, store_record

from .adapters import MetricsCollectorAdapter, PerformanceAnalyzerAdapter

logger = structlog.get_logger(__name__)

STAGE = "stage4_analyze"
CONTRACT_METRIC = "PerformanceMetricRecord"
CONTRACT_DIRECTIVE = "OptimizationDirectiveEnvelope"
CONTRACT_REDO = "RedoQueueItem"


class AnalyzeService:
    def __init__(
        self,
        metrics_collector: MetricsCollectorAdapter,
        performance_analyzer: PerformanceAnalyzerAdapter,
        *,
        default_collect_platform: Platform = Platform.TIKTOK,
    ) -> None:
        self._metrics_collector = metrics_collector
        self._performance_analyzer = performance_analyzer
        self._default_collect_platform = default_collect_platform

    async def collect_metrics(self, distribution_record_id: str) -> list[PerformanceMetricRecord]:
        platform = self._default_collect_platform
        metrics = await self._metrics_collector.collect(distribution_record_id, platform)
        for m in metrics:
            await store_record(
                CONTRACT_METRIC,
                STAGE,
                m.model_dump(mode="json"),
                identity_id=m.identity_id,
            )
        await log_audit(
            STAGE,
            "collect_metrics",
            distribution_record_id=distribution_record_id,
            platform=platform.value,
            metric_count=len(metrics),
        )
        logger.info(
            "metrics_collected",
            distribution_record_id=distribution_record_id,
            count=len(metrics),
        )
        return metrics

    async def analyze_performance(
        self, identity_id: str, window_hours: float = 24.0
    ) -> dict[str, Any]:
        metrics = await self._load_metrics_for_identity(identity_id, window_hours)
        by_type: dict[MetricType, list[float]] = defaultdict(list)
        for m in metrics:
            by_type[m.metric_type].append(m.value)

        aggregates: dict[str, Any] = {
            "identity_id": identity_id,
            "window_hours": window_hours,
            "metric_count": len(metrics),
            "by_metric_type": {
                k.value: {"count": len(v), "sum": sum(v), "avg": sum(v) / len(v) if v else 0.0}
                for k, v in by_type.items()
            },
        }

        await log_audit(
            STAGE,
            "analyze_performance",
            identity_id=identity_id,
            window_hours=window_hours,
            metric_count=len(metrics),
        )
        logger.info("performance_analyzed", identity_id=identity_id, metric_count=len(metrics))
        return aggregates

    async def generate_optimization(self, identity_id: str) -> OptimizationDirectiveEnvelope:
        metrics = await self._load_metrics_for_identity(identity_id, window_hours=24.0)
        envelope = await self._performance_analyzer.analyze(metrics)
        envelope = envelope.model_copy(update={"identity_id": identity_id})
        await store_record(
            CONTRACT_DIRECTIVE,
            STAGE,
            envelope.model_dump(mode="json"),
            identity_id=identity_id,
        )
        await log_audit(
            STAGE,
            "generate_optimization",
            identity_id=identity_id,
            directive_count=len(envelope.directives),
            confidence=envelope.confidence,
        )
        logger.info(
            "optimization_generated",
            identity_id=identity_id,
            directives=len(envelope.directives),
        )
        return envelope

    async def queue_redo(
        self,
        identity_id: str,
        content_id: str,
        reason: RedoReason,
        target_stage: int,
    ) -> RedoQueueItem:
        item = RedoQueueItem(
            identity_id=identity_id,
            original_content_id=content_id,
            target_stage=target_stage,
            reason=reason,
        )
        await store_record(
            CONTRACT_REDO,
            STAGE,
            item.model_dump(mode="json"),
            identity_id=identity_id,
        )
        await log_audit(
            STAGE,
            "queue_redo",
            identity_id=identity_id,
            content_id=content_id,
            reason=reason.value,
            target_stage=target_stage,
        )
        logger.info(
            "redo_queued",
            identity_id=identity_id,
            content_id=content_id,
            target_stage=target_stage,
        )
        return item

    async def list_stored_metrics(self, identity_id: str | None = None) -> list[PerformanceMetricRecord]:
        rows = await self._fetch_pipeline_rows(CONTRACT_METRIC, identity_id)
        return [PerformanceMetricRecord.model_validate(json.loads(r.data)) for r in rows]

    async def list_stored_directives(
        self, identity_id: str | None = None
    ) -> list[OptimizationDirectiveEnvelope]:
        rows = await self._fetch_pipeline_rows(CONTRACT_DIRECTIVE, identity_id)
        return [OptimizationDirectiveEnvelope.model_validate(json.loads(r.data)) for r in rows]

    async def _fetch_pipeline_rows(
        self, contract_type: str, identity_id: str | None
    ) -> list[PipelineRecord]:
        session = await get_async_session()
        async with session:
            q = select(PipelineRecord).where(PipelineRecord.contract_type == contract_type)
            if identity_id is not None:
                q = q.where(PipelineRecord.identity_id == identity_id)
            result = await session.execute(q)
            return list(result.scalars().all())

    async def _load_metrics_for_identity(
        self, identity_id: str, window_hours: float
    ) -> list[PerformanceMetricRecord]:
        cutoff = utc_now() - timedelta(hours=window_hours)
        rows = await self._fetch_pipeline_rows(CONTRACT_METRIC, identity_id)
        out: list[PerformanceMetricRecord] = []
        for row in rows:
            m = PerformanceMetricRecord.model_validate(json.loads(row.data))
            measured = m.measured_at
            if measured.tzinfo is None:
                measured = measured.replace(tzinfo=cutoff.tzinfo)
            if measured >= cutoff:
                out.append(m)
        return out
