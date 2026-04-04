"""Hackathon pipelines: Browser Use, TwelveLabs, Gemini orchestration, Veo 3.1."""

from __future__ import annotations

from dataclasses import dataclass

from browser_runtime.providers.mock import MockProvider

from hackathon_pipelines.adapters.facade import BrowserProviderFacade
from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, TwelveLabsUnderstanding, VeoVideoGenerator
from hackathon_pipelines.contracts import OrchestratorRunSummary
from hackathon_pipelines.orchestrator import HackathonOrchestrator
from hackathon_pipelines.pipelines.product_discovery import ProductDiscoveryPipeline
from hackathon_pipelines.pipelines.reel_discovery import ReelDiscoveryPipeline
from hackathon_pipelines.pipelines.social_media import SocialMediaPipeline
from hackathon_pipelines.pipelines.video_generation import VideoGenerationPipeline
from hackathon_pipelines.stores.memory import (
    MemoryAnalyticsSink,
    MemoryProductCatalog,
    MemoryReelSink,
    MemoryTemplateStore,
)


@dataclass(frozen=True)
class DryRunStack:
    orchestrator: HackathonOrchestrator
    templates: MemoryTemplateStore
    analytics: MemoryAnalyticsSink


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


__all__ = [
    "BrowserProviderFacade",
    "DryRunStack",
    "GeminiTemplateAgent",
    "HackathonOrchestrator",
    "MemoryAnalyticsSink",
    "MemoryProductCatalog",
    "MemoryReelSink",
    "MemoryTemplateStore",
    "OrchestratorRunSummary",
    "ProductDiscoveryPipeline",
    "ReelDiscoveryPipeline",
    "SocialMediaPipeline",
    "TwelveLabsUnderstanding",
    "VideoGenerationPipeline",
    "VeoVideoGenerator",
    "build_dry_run_orchestrator",
    "build_dry_run_stack",
]
