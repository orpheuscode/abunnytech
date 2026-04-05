"""Hackathon pipelines: Browser Use, TwelveLabs, Gemini orchestration, Veo 3.1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from browser_runtime.providers.base import BrowserProvider
from browser_runtime.providers.mock import MockProvider

from hackathon_pipelines.adapters.facade import BrowserProviderFacade
from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, TwelveLabsUnderstanding, VeoVideoGenerator
from hackathon_pipelines.contracts import OrchestratorRunSummary
from hackathon_pipelines.gemini_tool_orchestrator import (
    GeminiOrchestrationResult,
    dispatch_pipeline_tool,
    run_gemini_pipeline_orchestration,
)
from hackathon_pipelines.loop_runner import ContinuousLoopRunner, LoopRunnerConfig
from hackathon_pipelines.orchestrator import HackathonOrchestrator
from hackathon_pipelines.pipelines.product_discovery import ProductDiscoveryPipeline
from hackathon_pipelines.pipelines.reel_discovery import ReelDiscoveryPipeline
from hackathon_pipelines.pipelines.social_media import SocialMediaPipeline
from hackathon_pipelines.pipelines.video_generation import VideoGenerationPipeline
from hackathon_pipelines.ports import (
    AnalyticsSinkPort,
    GeminiVideoAgentPort,
    ProductCatalogPort,
    ReelMetadataSinkPort,
    TemplateStorePort,
    VeoGeneratorPort,
    VideoUnderstandingPort,
)
from hackathon_pipelines.scoring import (
    DEFAULT_PRODUCT_SCORE_WEIGHTS,
    ProductScoreWeights,
    best_product,
    product_score_breakdown,
    rank_products,
    score_product,
)
from hackathon_pipelines.stores import (
    MemoryAnalyticsSink,
    MemoryProductCatalog,
    MemoryReelSink,
    MemoryTemplateStore,
    SQLiteAnalyticsSink,
    SQLiteHackathonStore,
    SQLiteProductCatalog,
    SQLiteReelSink,
    SQLiteTemplateStore,
)


@dataclass(frozen=True)
class DryRunStack:
    orchestrator: HackathonOrchestrator
    templates: MemoryTemplateStore
    analytics: MemoryAnalyticsSink


@dataclass(frozen=True)
class RuntimeStack:
    orchestrator: HackathonOrchestrator
    templates: TemplateStorePort
    analytics: AnalyticsSinkPort
    products: ProductCatalogPort
    reels: ReelMetadataSinkPort
    store_path: Path


def build_dry_run_stack() -> DryRunStack:
    """Wire all pipelines with in-memory stores and API dry-run shims (safe for CI)."""

    browser = BrowserProviderFacade(MockProvider(dry_run=True))
    templates = MemoryTemplateStore()
    analytics = MemoryAnalyticsSink()
    reels = ReelDiscoveryPipeline(
        browser=browser,
        video_understanding=TwelveLabsUnderstanding(dry_run=True),
        templates=templates,
        reel_sink=MemoryReelSink(),
        gemini=GeminiTemplateAgent(dry_run=True),
    )
    products = ProductDiscoveryPipeline(browser=browser, catalog=MemoryProductCatalog())
    video = VideoGenerationPipeline(
        gemini=GeminiTemplateAgent(dry_run=True),
        veo=VeoVideoGenerator(dry_run=True),
    )
    social = SocialMediaPipeline(
        browser=browser,
        analytics_sink=analytics,
        templates=templates,
    )
    orch = HackathonOrchestrator(
        reel_discovery=reels,
        video_generation=video,
        social=social,
        products=products,
        templates=templates,
    )
    return DryRunStack(orchestrator=orch, templates=templates, analytics=analytics)


def build_dry_run_orchestrator() -> HackathonOrchestrator:
    return build_dry_run_stack().orchestrator


def build_runtime_stack(
    *,
    dry_run: bool = True,
    db_path: str | Path = Path("data") / "hackathon_pipelines.sqlite3",
    browser_provider: BrowserProvider | None = None,
    video_understanding: VideoUnderstandingPort | None = None,
    gemini: GeminiVideoAgentPort | None = None,
    veo: VeoGeneratorPort | None = None,
) -> RuntimeStack:
    """Build a persistent hackathon stack backed by SQLite.

    Dry-run mode works with the built-in mock provider and dry-run adapter shims.
    For live runs, inject the Browser Use provider and Veo adapter once the team
    snippets are ready. Gemini and TwelveLabs can still use the current built-in
    adapters unless callers supply their own.
    """

    resolved_db_path = Path(db_path)
    if browser_provider is None:
        if dry_run:
            browser_provider = MockProvider(dry_run=True)
        else:
            msg = "Inject a live Browser Use provider once the team snippet is ready."
            raise RuntimeError(msg)

    if veo is None and not dry_run:
        msg = "Inject a live Veo generator once the team snippet is ready."
        raise RuntimeError(msg)

    store = SQLiteHackathonStore(resolved_db_path)
    browser = BrowserProviderFacade(browser_provider)
    templates = SQLiteTemplateStore(store=store)
    analytics = SQLiteAnalyticsSink(store=store)
    reels = SQLiteReelSink(store=store)
    products = SQLiteProductCatalog(store=store)
    reels_pipeline = ReelDiscoveryPipeline(
        browser=browser,
        video_understanding=video_understanding or TwelveLabsUnderstanding(dry_run=dry_run),
        templates=templates,
        reel_sink=reels,
        gemini=gemini or GeminiTemplateAgent(dry_run=dry_run),
    )
    products_pipeline = ProductDiscoveryPipeline(browser=browser, catalog=products)
    video_pipeline = VideoGenerationPipeline(
        gemini=gemini or GeminiTemplateAgent(dry_run=dry_run),
        veo=veo or VeoVideoGenerator(dry_run=True),
    )
    social = SocialMediaPipeline(
        browser=browser,
        analytics_sink=analytics,
        templates=templates,
    )
    orchestrator = HackathonOrchestrator(
        reel_discovery=reels_pipeline,
        video_generation=video_pipeline,
        social=social,
        products=products_pipeline,
        templates=templates,
    )
    return RuntimeStack(
        orchestrator=orchestrator,
        templates=templates,
        analytics=analytics,
        products=products,
        reels=reels,
        store_path=resolved_db_path,
    )


__all__ = [
    "BrowserProviderFacade",
    "ContinuousLoopRunner",
    "DEFAULT_PRODUCT_SCORE_WEIGHTS",
    "DryRunStack",
    "GeminiOrchestrationResult",
    "GeminiTemplateAgent",
    "HackathonOrchestrator",
    "LoopRunnerConfig",
    "MemoryAnalyticsSink",
    "MemoryProductCatalog",
    "MemoryReelSink",
    "MemoryTemplateStore",
    "OrchestratorRunSummary",
    "ProductScoreWeights",
    "ProductDiscoveryPipeline",
    "ReelDiscoveryPipeline",
    "RuntimeStack",
    "SocialMediaPipeline",
    "SQLiteAnalyticsSink",
    "SQLiteHackathonStore",
    "SQLiteProductCatalog",
    "SQLiteReelSink",
    "SQLiteTemplateStore",
    "TwelveLabsUnderstanding",
    "VideoGenerationPipeline",
    "VeoVideoGenerator",
    "best_product",
    "build_dry_run_orchestrator",
    "build_dry_run_stack",
    "build_runtime_stack",
    "dispatch_pipeline_tool",
    "product_score_breakdown",
    "rank_products",
    "run_gemini_pipeline_orchestration",
    "score_product",
]
