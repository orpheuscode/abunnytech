"""
Stage 4 orchestration runner.

Wires together: ingestion → analysis → directive generation → redo queue →
baseline update → summary write → state persistence → audit log.

Can be run in dry_run mode (default True) — all side effects are logged
but nothing is written to external systems.

Usage:
    from agents.stage4_analytics.runner import Stage4Runner

    runner = Stage4Runner(dry_run=True)
    result = await runner.run(distribution_records)
    print(result.summary_daily)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .analysis_engine import AnalysisEngine, AnalyticsConfig
from .baseline import BaselineUpdater, SummaryWriter
from .contracts import (
    DistributionRecord,
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    RedoQueueItem,
)
from .directive_generator import DirectiveGenerator
from .ingestion import AbstractMetricsIngester, MockMetricsIngester
from .models import AnalysisBundle
from .redo_queue import RedoConfig, RedoQueueGenerator
from .retention import AbstractRetentionParser, MockRetentionParser
from .state_adapter import StateAdapter


@dataclass
class Stage4Result:
    metrics: list[PerformanceMetricRecord] = field(default_factory=list)
    bundle: AnalysisBundle | None = None
    directives: list[OptimizationDirectiveEnvelope] = field(default_factory=list)
    redo_items: list[RedoQueueItem] = field(default_factory=list)
    summary_daily: str = ""
    summary_weekly: str = ""
    dry_run: bool = True


class Stage4Runner:
    """
    Full Stage 4 pipeline.

    In dry_run=True mode:
      - Metrics are fetched (from mock/API) and analysed
      - Directives and redo items are generated
      - Everything is persisted to SQLite
      - No external mutations are made

    In dry_run=False mode:
      - Same as above, but the state adapter receives live data and
        directives are also written to the audit log for consumption
        by downstream stage pollers.
    """

    def __init__(
        self,
        dry_run: bool = True,
        ingester: AbstractMetricsIngester | None = None,
        retention_parser: AbstractRetentionParser | None = None,
        state_adapter: StateAdapter | None = None,
        analytics_config: AnalyticsConfig | None = None,
        redo_config: RedoConfig | None = None,
        niche: str = "general",
        db_path: str = "./data/stage4_analytics.db",
        fixture_path: str | None = None,
    ) -> None:
        self._dry_run = dry_run
        self._niche = niche
        self._adapter = state_adapter or StateAdapter(db_path=db_path)
        self._ingester = ingester or MockMetricsIngester(fixture_path=fixture_path)
        self._retention_parser = retention_parser or MockRetentionParser(fixture_path=fixture_path)
        self._engine = AnalysisEngine(config=analytics_config)
        self._directive_gen = DirectiveGenerator()
        self._redo_gen = RedoQueueGenerator(config=redo_config)
        self._baseline_updater = BaselineUpdater(self._adapter)
        self._summary_writer = SummaryWriter()

    async def run(
        self,
        distribution_records: list[DistributionRecord],
        window_days: int = 7,
    ) -> Stage4Result:
        """
        Full pipeline run. Returns a Stage4Result with all outputs.
        """
        result = Stage4Result(dry_run=self._dry_run)

        # 1. Ingest metrics
        result.metrics = await self._ingester.batch_fetch(distribution_records)
        self._adapter.save_metrics(result.metrics)

        # 2. Analyse
        result.bundle = self._engine.analyse(result.metrics, window_days=window_days)

        # 3. Generate directives
        result.directives = self._directive_gen.generate(result.bundle, dry_run=self._dry_run)
        self._adapter.save_directives(result.directives)

        # 4. Generate redo queue
        existing_retries = {
            item.source_distribution_record_id: item.retry_count
            for item in self._adapter.load_redo_queue(status=None)
        }
        result.redo_items = self._redo_gen.generate(
            result.metrics, existing_retry_counts=existing_retries, dry_run=self._dry_run
        )
        self._adapter.save_redo_items(result.redo_items)

        # 5. Update baselines
        self._baseline_updater.update(result.metrics, niche=self._niche)

        # 6. Write summaries
        result.summary_daily = self._summary_writer.daily(
            bundle=result.bundle,
            directives=result.directives,
            redo_items=result.redo_items,
        )

        return result

    async def run_weekly(
        self,
        distribution_records: list[DistributionRecord],
    ) -> Stage4Result:
        """
        Run analysis across the last 7 days (one bundle per day segment) and
        produce a weekly summary. For the hackathon demo, all records are
        analysed as one 7-day window.
        """
        result = await self.run(distribution_records, window_days=7)
        result.summary_weekly = self._summary_writer.weekly(
            bundles=[result.bundle] if result.bundle else [],
            directives=result.directives,
            redo_items=result.redo_items,
        )
        return result
