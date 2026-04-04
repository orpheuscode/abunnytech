"""FastAPI control plane that orchestrates all pipeline stages."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from packages.shared.config import get_settings
from packages.shared.db import init_db
from packages.shared.feature_flags import is_dry_run, is_enabled

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info(
        "control_plane.startup",
        dry_run=settings.dry_run,
        stage5_enabled=settings.feature_stage5_monetize,
    )
    await init_db()
    log.info("control_plane.db_initialized")
    yield
    log.info("control_plane.shutdown")


app = FastAPI(
    title="abunnytech - Autonomous AI Creator Pipeline",
    description="Control plane for the autonomous AI content creator pipeline.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Mount stage routers ---
from stages.stage0_identity.router import router as identity_router  # noqa: E402
from stages.stage1_discover.router import router as discover_router  # noqa: E402
from stages.stage2_generate.router import router as generate_router  # noqa: E402
from stages.stage3_distribute.router import router as distribute_router  # noqa: E402
from stages.stage4_analyze.router import router as analyze_router  # noqa: E402
from stages.stage5_monetize.router import router as monetize_router  # noqa: E402

app.include_router(identity_router)
app.include_router(discover_router)
app.include_router(generate_router)
app.include_router(distribute_router)
app.include_router(analyze_router)
app.include_router(monetize_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "abunnytech",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "dry_run": is_dry_run(),
        "stage5_monetize": is_enabled("stage5_monetize"),
    }


@app.post("/pipeline/demo")
async def run_demo_pipeline() -> dict[str, Any]:
    """Run a complete demo pipeline: identity -> discover -> generate -> distribute -> analyze.

    This is the single-button hackathon demo endpoint.
    """
    from stages.stage0_identity.service import create_default_identity
    from stages.stage1_discover.service import get_discovery_service
    from stages.stage2_generate.service import ContentGenerationService
    from stages.stage3_distribute.service import DistributionService
    from stages.stage4_analyze.adapters import MockMetricsCollector, MockPerformanceAnalyzer
    from stages.stage4_analyze.service import AnalyzeService

    results: dict[str, Any] = {"stages": {}}

    # Stage 0: Create identity
    log.info("demo.stage0.start")
    identity = await create_default_identity()
    identity_id = str(identity.id)
    results["stages"]["stage0_identity"] = {
        "identity_id": identity_id,
        "name": identity.name,
        "archetype": identity.archetype.value,
    }

    # Stage 1: Discover trends
    log.info("demo.stage1.start", identity_id=identity_id)
    discovery = get_discovery_service()
    from packages.contracts.base import Platform

    trends = await discovery.discover_trending(Platform.TIKTOK, identity_id)
    results["stages"]["stage1_discover"] = {
        "trending_count": len(trends),
        "top_trend": trends[0].title if trends else None,
    }

    # Stage 2: Generate content
    log.info("demo.stage2.start", identity_id=identity_id)
    generator = ContentGenerationService()
    topic = trends[0].title if trends else "AI productivity hacks"
    blueprint = await generator.create_blueprint(
        identity_id=identity_id,
        title=f"Quick take: {topic}",
        topic=topic,
        platform=Platform.TIKTOK,
    )
    package = await generator.render_content(str(blueprint.id))
    results["stages"]["stage2_generate"] = {
        "blueprint_id": str(blueprint.id),
        "package_id": str(package.id),
        "title": package.title,
        "scene_count": len(blueprint.scenes),
    }

    # Stage 3: Distribute (dry-run)
    log.info("demo.stage3.start", identity_id=identity_id)
    distributor = DistributionService()
    dist_record = await distributor.post_content(
        content_package_id=str(package.id),
        platform=Platform.TIKTOK,
        dry_run=True,
    )
    replies = await distributor.reply_to_comments(
        distribution_record_id=str(dist_record.id),
        identity_id=identity_id,
    )
    results["stages"]["stage3_distribute"] = {
        "distribution_id": str(dist_record.id),
        "status": dist_record.status.value,
        "dry_run": dist_record.dry_run,
        "reply_count": len(replies),
    }

    # Stage 4: Analyze
    log.info("demo.stage4.start", identity_id=identity_id)
    analyzer = AnalyzeService(
        metrics_collector=MockMetricsCollector(),
        performance_analyzer=MockPerformanceAnalyzer(),
    )
    metrics = await analyzer.collect_metrics(str(dist_record.id))
    optimization = await analyzer.generate_optimization(identity_id)
    results["stages"]["stage4_analyze"] = {
        "metrics_collected": len(metrics),
        "optimization_directives": len(optimization.directives),
        "confidence": optimization.confidence,
    }

    results["demo_complete"] = True
    results["identity_id"] = identity_id
    log.info("demo.complete", identity_id=identity_id)
    return results
