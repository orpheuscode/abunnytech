"""
Stage 4 — Analyze & Adapt

Entry points:
    Stage4Runner     — full pipeline orchestrator
    AnalysisEngine   — standalone dimension analyser
    DirectiveGenerator — converts AnalysisBundle → OptimizationDirectiveEnvelope
    RedoQueueGenerator — flags underperforming posts for regeneration
    StateAdapter     — SQLite persistence layer
    MockMetricsIngester — fixture-driven ingester for tests + dry runs
"""
from .analysis_engine import AnalysisEngine, AnalyticsConfig
from .baseline import BaselineUpdater, SummaryWriter
from .contracts import (
    ContentPackage,
    DistributionRecord,
    IdentityMatrix,
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    ProductCatalogItem,
    RedoQueueItem,
    VideoBlueprint,
)
from .directive_generator import DirectiveGenerator
from .ingestion import AbstractMetricsIngester, MockMetricsIngester
from .models import AnalysisBundle, AnalysisDimension, AnalysisResult, BaselineSnapshot
from .redo_queue import RedoConfig, RedoQueueGenerator
from .retention import MockRetentionParser, RetentionCurve
from .runner import Stage4Result, Stage4Runner
from .state_adapter import StateAdapter

__all__ = [
    "Stage4Runner",
    "Stage4Result",
    "AnalysisEngine",
    "AnalyticsConfig",
    "DirectiveGenerator",
    "RedoQueueGenerator",
    "RedoConfig",
    "MockMetricsIngester",
    "AbstractMetricsIngester",
    "MockRetentionParser",
    "RetentionCurve",
    "StateAdapter",
    "BaselineUpdater",
    "SummaryWriter",
    "AnalysisBundle",
    "AnalysisDimension",
    "AnalysisResult",
    "BaselineSnapshot",
    # Contracts
    "PerformanceMetricRecord",
    "OptimizationDirectiveEnvelope",
    "RedoQueueItem",
    "DistributionRecord",
    "ContentPackage",
    "VideoBlueprint",
    "IdentityMatrix",
    "ProductCatalogItem",
]
