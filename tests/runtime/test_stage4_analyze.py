"""Tests for Stage 4 - Analyze & Adapt."""

from __future__ import annotations

import pytest

from packages.contracts.analytics import RedoReason
from packages.shared.db import init_db
from stages.stage4_analyze.adapters import MockMetricsCollector, MockPerformanceAnalyzer
from stages.stage4_analyze.service import AnalyzeService


@pytest.mark.asyncio
async def test_collect_metrics():
    await init_db()
    svc = AnalyzeService(
        metrics_collector=MockMetricsCollector(),
        performance_analyzer=MockPerformanceAnalyzer(),
    )
    metrics = await svc.collect_metrics("test-dist-id")
    assert len(metrics) > 0


@pytest.mark.asyncio
async def test_generate_optimization():
    await init_db()
    svc = AnalyzeService(
        metrics_collector=MockMetricsCollector(),
        performance_analyzer=MockPerformanceAnalyzer(),
    )
    await svc.collect_metrics("test-dist-id")
    envelope = await svc.generate_optimization("demo-creator")
    assert len(envelope.directives) > 0


@pytest.mark.asyncio
async def test_queue_redo():
    await init_db()
    svc = AnalyzeService(
        metrics_collector=MockMetricsCollector(),
        performance_analyzer=MockPerformanceAnalyzer(),
    )
    item = await svc.queue_redo(
        identity_id="test-identity",
        content_id="test-content",
        reason=RedoReason.LOW_ENGAGEMENT,
        target_stage=2,
    )
    assert item.target_stage == 2
    assert item.processed is False
