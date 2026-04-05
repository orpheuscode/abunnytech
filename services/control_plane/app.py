"""FastAPI control plane that orchestrates all pipeline stages."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
    app.state.hackathon_loop_runner = None
    log.info("control_plane.db_initialized")
    yield
    runner = getattr(app.state, "hackathon_loop_runner", None)
    if runner is not None and runner.is_running:
        await runner.stop()
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
    runner = getattr(app.state, "hackathon_loop_runner", None)
    return {
        "status": "healthy",
        "dry_run": is_dry_run(),
        "stage5_monetize": is_enabled("stage5_monetize"),
        "hackathon_loop_running": bool(runner and runner.is_running),
    }


class HackathonDemoRequest(BaseModel):
    dry_run: bool | None = None
    niche_query: str | None = None
    caption: str | None = None
    product_image_path: str | None = None
    avatar_image_path: str | None = None
    media_path: str | None = None
    db_path: str | None = None


class HackathonLoopRequest(BaseModel):
    dry_run: bool | None = None
    interval_seconds: float | None = Field(default=None, gt=0)
    max_cycles: int | None = Field(default=None, ge=1)
    niche_query: str | None = None
    caption: str | None = None
    workdir: str | None = None


def _ensure_asset(path_str: str, *, dry_run: bool) -> str:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run and not path.exists():
        path.write_bytes(b"")
    if not dry_run and not path.exists():
        msg = f"Required asset does not exist: {path}"
        raise HTTPException(status_code=400, detail=msg)
    return str(path)


def _hackathon_defaults(payload: HackathonDemoRequest, *, dry_run: bool) -> dict[str, str]:
    settings = get_settings()
    return {
        "product_image_path": _ensure_asset(
            payload.product_image_path or settings.hackathon_product_image_path,
            dry_run=dry_run,
        ),
        "avatar_image_path": _ensure_asset(
            payload.avatar_image_path or settings.hackathon_avatar_image_path,
            dry_run=dry_run,
        ),
        "media_path": _ensure_asset(
            payload.media_path or settings.hackathon_media_path,
            dry_run=dry_run,
        ),
    }


def _build_hackathon_stack(*, dry_run: bool, db_path: str | None):
    from hackathon_pipelines import build_runtime_stack

    settings = get_settings()
    try:
        return build_runtime_stack(
            dry_run=dry_run,
            db_path=db_path or settings.hackathon_pipeline_db_path,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/pipeline/demo")
async def run_demo_pipeline(payload: HackathonDemoRequest | None = None) -> dict[str, Any]:
    from hackathon_pipelines.contracts import ClosedLoopRunSummary

    settings = get_settings()
    request = payload or HackathonDemoRequest()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    assets = _hackathon_defaults(request, dry_run=dry_run)
    stack = _build_hackathon_stack(dry_run=dry_run, db_path=request.db_path)
    summary: ClosedLoopRunSummary = await stack.orchestrator.run_closed_loop_cycle(
        product_image_path=assets["product_image_path"],
        avatar_image_path=assets["avatar_image_path"],
        niche_query=request.niche_query or settings.hackathon_niche_query,
        caption=request.caption or settings.hackathon_default_caption,
        media_path=assets["media_path"],
        dry_run=dry_run,
    )
    return {
        "demo_complete": True,
        "pipeline": "hackathon_closed_loop",
        "dry_run": dry_run,
        "db_path": str(stack.store_path),
        "product_image_path": assets["product_image_path"],
        "avatar_image_path": assets["avatar_image_path"],
        "media_path": summary.media_path,
        "summary": summary.model_dump(mode="json"),
    }


@app.post("/pipeline/stage-demo")
async def run_stage_demo_pipeline() -> dict[str, Any]:
    """Run a complete demo pipeline: identity -> discover -> generate -> distribute -> analyze.

    Legacy stage-by-stage demo preserved for the existing stage stack.
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


@app.get("/pipeline/loop/status")
async def hackathon_loop_status() -> dict[str, Any]:
    runner = getattr(app.state, "hackathon_loop_runner", None)
    if runner is None:
        return {
            "running": False,
            "configured": False,
            "cycle_count": 0,
            "last_started_at": None,
            "last_finished_at": None,
            "next_run_at": None,
            "last_error": None,
            "last_cycle": None,
        }
    status = asdict(runner.status())
    status["configured"] = True
    return status


@app.post("/pipeline/loop/start")
async def start_hackathon_loop(payload: HackathonLoopRequest | None = None) -> dict[str, Any]:
    from hackathon_pipelines import ContinuousLoopRunner, LoopRunnerConfig

    settings = get_settings()
    runner = getattr(app.state, "hackathon_loop_runner", None)
    if runner is not None and runner.is_running:
        raise HTTPException(status_code=409, detail="Hackathon loop is already running.")

    request = payload or HackathonLoopRequest()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    stack = _build_hackathon_stack(dry_run=dry_run, db_path=None)
    config = LoopRunnerConfig(
        interval_seconds=request.interval_seconds or settings.hackathon_loop_interval_seconds,
        max_cycles=request.max_cycles if request.max_cycles is not None else settings.hackathon_loop_max_cycles,
        dry_run=dry_run,
        niche_query=request.niche_query or settings.hackathon_niche_query,
        caption=request.caption or settings.hackathon_default_caption,
        workdir=Path(request.workdir or settings.hackathon_loop_workdir),
    )
    runner = ContinuousLoopRunner(
        orchestrator=stack.orchestrator,
        templates=stack.templates,
        config=config,
    )
    app.state.hackathon_loop_runner = runner
    runner.start()
    status = asdict(runner.status())
    status["db_path"] = str(stack.store_path)
    return status


@app.post("/pipeline/loop/stop")
async def stop_hackathon_loop() -> dict[str, Any]:
    runner = getattr(app.state, "hackathon_loop_runner", None)
    if runner is None:
        return {"running": False, "stopped": True}
    await runner.stop()
    status = asdict(runner.status())
    status["stopped"] = True
    return status
