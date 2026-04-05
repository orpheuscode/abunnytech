"""FastAPI control plane that orchestrates all pipeline stages."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from hackathon_pipelines.contracts import CommentEngagementPersona
from pydantic import BaseModel, Field

from packages.shared.config import get_settings
from packages.shared.db import init_db
from packages.shared.feature_flags import is_dry_run, is_enabled
from services.control_plane.database_explorer import discover_databases, get_database_detail

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
    app.state.instant_demo_tasks = set()
    log.info("control_plane.db_initialized")
    yield
    runner = getattr(app.state, "hackathon_loop_runner", None)
    if runner is not None and runner.is_running:
        await runner.stop()
    instant_demo_tasks = getattr(app.state, "instant_demo_tasks", set())
    if instant_demo_tasks:
        for task in list(instant_demo_tasks):
            task.cancel()
        await asyncio.gather(*instant_demo_tasks, return_exceptions=True)
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


class BrowserRuntimeRequest(BaseModel):
    cdp_url: str | None = None
    chrome_executable_path: str | None = None
    chrome_user_data_dir: str | None = None
    chrome_profile_directory: str | None = None
    headless: bool | None = None


class HackathonDemoRequest(BaseModel):
    dry_run: bool | None = None
    niche_query: str | None = None
    caption: str | None = None
    product_image_path: str | None = None
    avatar_image_path: str | None = None
    product_title: str | None = None
    product_description: str | None = None
    engagement_persona: CommentEngagementPersona | None = None
    media_path: str | None = None
    db_path: str | None = None
    browser_runtime: BrowserRuntimeRequest | None = None


class InstantDemoRequest(HackathonDemoRequest):
    start_background_generation: bool = True


class HackathonLoopRequest(BaseModel):
    dry_run: bool | None = None
    interval_seconds: float | None = Field(default=None, gt=0)
    max_cycles: int | None = Field(default=None, ge=1)
    niche_query: str | None = None
    caption: str | None = None
    workdir: str | None = None
    browser_runtime: BrowserRuntimeRequest | None = None


class GeminiOrchestrationRequest(BaseModel):
    instruction: str = (
        "Run the full storefront pipeline end to end: discover winning reels, build templates, "
        "pick the best product, generate the video, publish it, engage comments when live, and "
        "feed analytics back into the template store."
    )
    dry_run: bool | None = None
    niche_query: str | None = None
    caption: str | None = None
    product_image_path: str | None = None
    avatar_image_path: str | None = None
    product_title: str | None = None
    product_description: str | None = None
    media_path: str | None = None
    db_path: str | None = None
    max_turns: int = Field(default=12, ge=1, le=30)
    browser_runtime: BrowserRuntimeRequest | None = None


class PostLatestRunRequest(BaseModel):
    dry_run: bool | None = None
    run_id: str | None = None
    db_path: str | None = None
    browser_runtime: BrowserRuntimeRequest | None = None


class EngageLatestRunRequest(BaseModel):
    dry_run: bool | None = None
    run_id: str | None = None
    db_path: str | None = None
    browser_runtime: BrowserRuntimeRequest | None = None


class GenerateVideoFromDbRequest(BaseModel):
    dry_run: bool | None = None
    product_image_path: str | None = None
    avatar_image_path: str | None = None
    product_title: str | None = None
    product_description: str | None = None
    engagement_persona: CommentEngagementPersona | None = None
    db_path: str | None = None
    browser_runtime: BrowserRuntimeRequest | None = None


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


def _browser_runtime_env_from_request(
    browser_runtime: BrowserRuntimeRequest | None,
) -> dict[str, str] | None:
    if browser_runtime is None:
        return None
    payload = browser_runtime.model_dump(exclude_none=True)
    if not payload:
        return None

    env: dict[str, str] = {}
    if payload.get("cdp_url"):
        env["BROWSER_USE_CDP_URL"] = str(payload["cdp_url"])
    if payload.get("chrome_executable_path"):
        env["CHROME_EXECUTABLE_PATH"] = str(payload["chrome_executable_path"])
    if payload.get("chrome_user_data_dir"):
        env["CHROME_USER_DATA_DIR"] = str(payload["chrome_user_data_dir"])
    if payload.get("chrome_profile_directory"):
        env["CHROME_PROFILE_DIRECTORY"] = str(payload["chrome_profile_directory"])
    if "headless" in payload:
        env["BROWSER_USE_HEADLESS"] = str(bool(payload["headless"])).lower()
    return env or None


def _build_hackathon_stack(
    *,
    dry_run: bool,
    db_path: str | None,
    browser_runtime: BrowserRuntimeRequest | None = None,
):
    from hackathon_pipelines import build_runtime_stack

    settings = get_settings()
    try:
        return build_runtime_stack(
            dry_run=dry_run,
            db_path=db_path or settings.hackathon_pipeline_db_path,
            browser_runtime_env=_browser_runtime_env_from_request(browser_runtime),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_record_payload(record) -> dict[str, Any]:
    from hackathon_pipelines.dashboard_workflow import serialize_run_for_dashboard

    payload = serialize_run_for_dashboard(record)
    return payload or {}


def _track_instant_demo_task(task: asyncio.Task[Any]) -> None:
    task_set = getattr(app.state, "instant_demo_tasks", None)
    if task_set is None:
        task_set = set()
        app.state.instant_demo_tasks = task_set
    task_set.add(task)
    task.add_done_callback(task_set.discard)


@app.post("/pipeline/demo")
async def run_demo_pipeline(payload: HackathonDemoRequest | None = None) -> dict[str, Any]:
    from hackathon_pipelines.dashboard_workflow import run_dashboard_pipeline

    settings = get_settings()
    request = payload or HackathonDemoRequest()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    assets = _hackathon_defaults(request, dry_run=dry_run)
    stack = _build_hackathon_stack(
        dry_run=dry_run,
        db_path=request.db_path,
        browser_runtime=request.browser_runtime,
    )
    browser_runtime_env = _browser_runtime_env_from_request(request.browser_runtime)
    run_record = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=assets["product_image_path"],
        avatar_image_path=assets["avatar_image_path"],
        dry_run=dry_run,
        product_title=request.product_title,
        product_description=request.product_description,
        engagement_persona=request.engagement_persona,
        browser_runtime_env=browser_runtime_env,
    )
    return {
        "demo_complete": run_record.status.value != "failed",
        "pipeline": "hackathon_generate_ready",
        "dry_run": dry_run,
        "db_path": str(stack.store_path),
        "product_image_path": assets["product_image_path"],
        "avatar_image_path": assets["avatar_image_path"],
        "media_path": run_record.video_path,
        "run": _run_record_payload(run_record),
    }


@app.post("/pipeline/demo-mode")
async def run_instant_demo_mode(payload: InstantDemoRequest | None = None) -> dict[str, Any]:
    from hackathon_pipelines.dashboard_workflow import (
        run_parallel_demo_mode,
    )

    settings = get_settings()
    request = payload or InstantDemoRequest()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    assets = _hackathon_defaults(request, dry_run=dry_run)
    browser_runtime_env = _browser_runtime_env_from_request(request.browser_runtime)
    stack = _build_hackathon_stack(
        dry_run=dry_run,
        db_path=request.db_path,
        browser_runtime=request.browser_runtime,
    )
    notes: list[str] = []
    lanes = [
        "reel_discovery_to_video_structure",
        "video_structure_to_video_gen_and_instagram_posting",
        "comment_engagement",
    ]
    background_generation_started = False
    if request.start_background_generation:

        async def _run_parallel_demo_lanes() -> None:
            try:
                await run_parallel_demo_mode(
                    store=stack.store,
                    browser=stack.browser,
                    video_understanding=stack.video_understanding,
                    gemini=stack.gemini,
                    veo=stack.veo,
                    social=stack.social,
                    product_image_path=assets["product_image_path"],
                    avatar_image_path=assets["avatar_image_path"],
                    dry_run=dry_run,
                    product_title=request.product_title,
                    product_description=request.product_description,
                    engagement_persona=request.engagement_persona,
                    browser_runtime_env=browser_runtime_env,
                )
            except Exception:
                log.exception("control_plane.instant_demo.parallel_demo_mode_failed")

        task = asyncio.create_task(
            _run_parallel_demo_lanes(),
            name="instant-demo-parallel-lanes",
        )
        _track_instant_demo_task(task)
        background_generation_started = True
        notes.append(
            "Started three parallel demo lanes: reel discovery -> video structure, "
            "video structure -> video gen + Instagram posting, and comment engagement."
        )
    else:
        notes.append("Instant demo mode was requested without starting the parallel background lanes.")

    return {
        "ok": True,
        "pipeline": "instant_demo_mode",
        "dry_run": dry_run,
        "db_path": str(stack.store_path),
        "background_generation_started": background_generation_started,
        "parallel_lanes": lanes,
        "notes": notes,
    }


@app.post("/pipeline/gemini-orchestrate")
async def run_gemini_orchestration(
    payload: GeminiOrchestrationRequest | None = None,
) -> dict[str, Any]:
    from hackathon_pipelines import run_gemini_pipeline_orchestration

    settings = get_settings()
    request = payload or GeminiOrchestrationRequest()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    assets = _hackathon_defaults(
        HackathonDemoRequest(
            dry_run=dry_run,
            niche_query=request.niche_query,
            caption=request.caption,
            product_image_path=request.product_image_path,
            avatar_image_path=request.avatar_image_path,
            media_path=request.media_path,
            db_path=request.db_path,
        ),
        dry_run=dry_run,
    )
    stack = _build_hackathon_stack(
        dry_run=dry_run,
        db_path=request.db_path,
        browser_runtime=request.browser_runtime,
    )
    instruction = (
        f"{request.instruction.strip()}\n\n"
        "When tool parameters are required, use these exact values:\n"
        f'- niche_query: "{request.niche_query or settings.hackathon_niche_query}"\n'
        f'- caption: "{request.caption or settings.hackathon_default_caption}"\n'
        f'- product_image_path: "{assets["product_image_path"]}"\n'
        f'- avatar_image_path: "{assets["avatar_image_path"]}"\n'
        f'- media_path: "{assets["media_path"]}"\n'
        f"- dry_run: {str(dry_run).lower()}\n"
    )
    result = await run_gemini_pipeline_orchestration(
        stack.orchestrator,
        instruction=instruction,
        max_turns=request.max_turns,
    )
    return {
        "ok": True,
        "pipeline": "gemini_meta_orchestrator",
        "dry_run": dry_run,
        "db_path": str(stack.store_path),
        "product_image_path": assets["product_image_path"],
        "avatar_image_path": assets["avatar_image_path"],
        "media_path": assets["media_path"],
        "final_text": result.final_text,
        "tool_trace": result.tool_trace,
        "turns_used": result.turns_used,
    }


@app.get("/pipeline/latest-run")
async def latest_pipeline_run(db_path: str | None = None) -> dict[str, Any]:
    from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

    settings = get_settings()
    store = SQLiteHackathonStore(db_path or settings.hackathon_pipeline_db_path)
    record = store.latest_run()
    return {
        "ok": record is not None,
        "db_path": str(store.db_path),
        "run": _run_record_payload(record) if record is not None else None,
    }


@app.get("/pipeline/runs")
async def list_pipeline_runs(db_path: str | None = None, limit: int = 20) -> dict[str, Any]:
    from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

    settings = get_settings()
    store = SQLiteHackathonStore(db_path or settings.hackathon_pipeline_db_path)
    normalized_limit = max(1, min(limit, 100))
    runs = [_run_record_payload(record) for record in store.list_runs()[:normalized_limit]]
    return {
        "ok": True,
        "db_path": str(store.db_path),
        "count": len(runs),
        "runs": runs,
    }


@app.get("/pipeline/posts")
async def list_pipeline_posts(db_path: str | None = None) -> dict[str, Any]:
    from hackathon_pipelines.dashboard_workflow import serialize_post_for_dashboard
    from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

    settings = get_settings()
    store = SQLiteHackathonStore(db_path or settings.hackathon_pipeline_db_path)
    posts = [
        serialize_post_for_dashboard(
            record,
            replies=store.list_comment_replies(record.post_url),
        )
        for record in store.list_posted_content()
    ]
    return {
        "ok": True,
        "db_path": str(store.db_path),
        "posts": posts,
    }


@app.get("/pipeline/runs/{run_id}")
async def get_pipeline_run(run_id: str, db_path: str | None = None) -> dict[str, Any]:
    from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

    settings = get_settings()
    store = SQLiteHackathonStore(db_path or settings.hackathon_pipeline_db_path)
    record = store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")
    return {
        "ok": True,
        "db_path": str(store.db_path),
        "run": _run_record_payload(record),
    }


@app.post("/pipeline/post-latest")
async def post_latest_pipeline_run(payload: PostLatestRunRequest | None = None) -> dict[str, Any]:
    from hackathon_pipelines.dashboard_workflow import post_latest_run
    from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

    settings = get_settings()
    request = payload or PostLatestRunRequest()
    dry_run = False if request.dry_run is None else request.dry_run
    store = SQLiteHackathonStore(request.db_path or settings.hackathon_pipeline_db_path)
    stack = _build_hackathon_stack(
        dry_run=dry_run,
        db_path=str(store.db_path),
        browser_runtime=request.browser_runtime,
    )
    try:
        record, output = await post_latest_run(
            store=store,
            social=stack.social,
            dry_run=dry_run,
            run_id=request.run_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "dry_run": dry_run,
        "db_path": str(store.db_path),
        "run": _run_record_payload(record),
        "publish_output": output,
    }


@app.post("/pipeline/generate-video")
async def generate_video_pipeline_run(payload: GenerateVideoFromDbRequest | None = None) -> dict[str, Any]:
    from hackathon_pipelines.dashboard_workflow import generate_video_from_structure_db

    settings = get_settings()
    request = payload or GenerateVideoFromDbRequest()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    assets = _hackathon_defaults(
        HackathonDemoRequest(
            dry_run=dry_run,
            product_image_path=request.product_image_path,
            avatar_image_path=request.avatar_image_path,
        ),
        dry_run=dry_run,
    )
    stack = _build_hackathon_stack(
        dry_run=dry_run,
        db_path=request.db_path,
        browser_runtime=request.browser_runtime,
    )
    try:
        record = await generate_video_from_structure_db(
            store=stack.store,
            gemini=stack.gemini,
            veo=stack.veo,
            product_image_path=assets["product_image_path"],
            avatar_image_path=assets["avatar_image_path"],
            dry_run=dry_run,
            product_title=request.product_title,
            product_description=request.product_description,
            engagement_persona=request.engagement_persona,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": record.status != "failed",
        "dry_run": dry_run,
        "db_path": str(stack.store_path),
        "product_image_path": assets["product_image_path"],
        "avatar_image_path": assets["avatar_image_path"],
        "media_path": record.video_path,
        "run": _run_record_payload(record),
    }


@app.post("/pipeline/engage-latest")
async def engage_latest_pipeline_run(
    payload: EngageLatestRunRequest | None = None,
) -> dict[str, Any]:
    from hackathon_pipelines.dashboard_workflow import engage_latest_posted_run
    from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

    settings = get_settings()
    request = payload or EngageLatestRunRequest()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    store = SQLiteHackathonStore(request.db_path or settings.hackathon_pipeline_db_path)
    stack = _build_hackathon_stack(
        dry_run=dry_run,
        db_path=str(store.db_path),
        browser_runtime=request.browser_runtime,
    )
    try:
        record, summary = await engage_latest_posted_run(
            store=store,
            social=stack.social,
            dry_run=dry_run,
            run_id=request.run_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "dry_run": dry_run,
        "db_path": str(store.db_path),
        "run": _run_record_payload(record),
        "engagement_summary": summary.model_dump(mode="json"),
    }


@app.get("/pipeline/databases")
async def list_pipeline_databases() -> dict[str, Any]:
    settings = get_settings()
    return {
        "ok": True,
        "databases": discover_databases(settings),
    }


@app.get("/pipeline/databases/{db_key}")
async def database_detail(
    db_key: str, table: str | None = None, page: int = 1, page_size: int = 20
) -> dict[str, Any]:
    settings = get_settings()
    try:
        detail = get_database_detail(
            settings, db_key=db_key, table=table, page=page, page_size=page_size
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "ok": True,
        "database": detail,
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
    stack = _build_hackathon_stack(
        dry_run=dry_run,
        db_path=None,
        browser_runtime=request.browser_runtime,
    )
    config = LoopRunnerConfig(
        interval_seconds=request.interval_seconds or settings.hackathon_loop_interval_seconds,
        max_cycles=request.max_cycles
        if request.max_cycles is not None
        else settings.hackathon_loop_max_cycles,
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
