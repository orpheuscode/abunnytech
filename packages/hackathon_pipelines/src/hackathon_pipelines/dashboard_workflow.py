"""Dashboard-oriented end-to-end workflow helpers for the hackathon pipeline."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from hackathon_pipelines.adapters.instagram_download_api import InstagramDownloadAPI
from hackathon_pipelines.adapters.instagram_instaloader import InstagramInstaloaderDownloader
from hackathon_pipelines.contracts import (
    CommentEngagementPersona,
    CommentEngagementSummary,
    HackathonRunRecord,
    HackathonRunStatus,
    InstagramPostDraft,
    PostAnalyticsSnapshot,
    PostedContentRecord,
    PostJob,
    ReelSurfaceMetrics,
)
from hackathon_pipelines.pipelines.db_to_video_generation import generate_video_from_best_db_template
from hackathon_pipelines.pipelines.reel_discovery import (
    BrowserUseDiscoveredReels,
    ReelDiscoverySearchConfig,
    _build_reel_discovery_task,
    build_instagram_reels_browser_use_metadata,
    run_parallel_reel_discovery,
)
from hackathon_pipelines.pipelines.social_media import (
    _extract_instagram_post_id,
    normalize_comment_engagement_persona,
)
from hackathon_pipelines.ports import BrowserAutomationPort, GeminiVideoAgentPort, VideoUnderstandingPort
from hackathon_pipelines.stores.memory import new_id
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

DEFAULT_TEMP_VIDEO_DIR = Path("data") / "tmp_reels_instaloader"
DEFAULT_MIN_LIKES = 500
DEFAULT_MIN_COMMENTS = 20
DEFAULT_DOWNLOAD_ATTEMPTS_PER_BACKEND = 2
DEFAULT_DOWNLOAD_ATTEMPT_TIMEOUT_SECONDS = 180.0
DEFAULT_DOWNLOAD_RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_DEMO_ANALYTICS_RETENTION_CURVE_PCT = {
    "0": 100,
    "1": 91,
    "2": 80,
    "3": 72,
    "5": 57,
    "7": 45,
    "10": 33,
    "13": 24,
    "15": 20,
}
DEFAULT_DEMO_ANALYTICS_TIMELINE = (
    ("day_1", 1, 2_700, 210, 16, 10, 58, 4, "launch_day_discovery"),
    ("day_3", 3, 8_900, 690, 41, 24, 190, 11, "algorithm_pickup"),
    ("week_1", 7, 23_800, 1_760, 96, 63, 438, 29, "compound_replays"),
)


class DemoAnalyticsSeedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_url: str
    post_id: str
    snapshot_ids: list[str] = Field(default_factory=list)
    scheduled_checks: list[str] = Field(default_factory=list)
    retention_takeaway: str = ""
    adaptation_recommendation: str = ""
    performance_label: str | None = None


def _build_dashboard_discovery_task() -> tuple[str, dict[str, Any]]:
    description = _build_reel_discovery_task(
        ReelDiscoverySearchConfig(
            discovery_mode="feed_scroll",
            target_good_reels=5,
        )
    )
    metadata = build_instagram_reels_browser_use_metadata()
    assert metadata["browser_use_output_model_schema"] is BrowserUseDiscoveredReels
    return description, metadata


def _qualifying_reels(
    metrics: list[ReelSurfaceMetrics],
    *,
    min_likes: int = DEFAULT_MIN_LIKES,
    min_comments: int = DEFAULT_MIN_COMMENTS,
) -> list[ReelSurfaceMetrics]:
    qualifying: list[ReelSurfaceMetrics] = []
    for metric in metrics:
        if metric.is_ugc_candidate is not True:
            continue
        if metric.likes < min_likes or metric.comments < min_comments:
            continue
        qualifying.append(metric)
    return qualifying


def _dry_run_metric() -> ReelSurfaceMetrics:
    return ReelSurfaceMetrics(
        reel_id=new_id("reel"),
        source_url="https://www.instagram.com/reel/dry_run/",
        views=42_000,
        likes=1_800,
        comments=140,
        creator_handle="dryrun.creator",
        caption_text="Creator-style demo of a product with a strong opening hook.",
        is_ugc_candidate=True,
        ugc_reason="dry_run_seed",
    )


def _already_processed_reel_ids(store: SQLiteHackathonStore) -> set[str]:
    return {record.source_reel_id for record in store.list_structures()}


async def discover_reels_to_store(
    *,
    browser: BrowserAutomationPort,
    store: SQLiteHackathonStore,
    min_likes: int = DEFAULT_MIN_LIKES,
    min_comments: int = DEFAULT_MIN_COMMENTS,
    agent_count: int | None = None,
    browser_runtime_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    description, metadata = _build_dashboard_discovery_task()
    metrics, results = await run_parallel_reel_discovery(
        browser=browser,
        search_config=ReelDiscoverySearchConfig(
            discovery_mode="feed_scroll",
            target_good_reels=5,
        ),
        max_steps=28,
        agent_count=agent_count,
        browser_runtime_env=browser_runtime_env,
    )
    if not metrics and any(result.dry_run for result in results):
        metrics = [_dry_run_metric()]
    qualifying = _qualifying_reels(metrics, min_likes=min_likes, min_comments=min_comments)
    if qualifying:
        store.upsert_reel_metrics(qualifying)
    succeeded = [result for result in results if result.success]
    failed = [result for result in results if not result.success]
    return {
        "browser_success": bool(succeeded),
        "browser_error": None if succeeded else "; ".join(result.error or result.task_id for result in failed),
        "agent_count": len(results),
        "successful_agent_runs": len(succeeded),
        "failed_agent_runs": len(failed),
        "parsed_metrics_count": len(metrics),
        "queued_reels_count": len(qualifying),
        "agent_runs": [
            {
                "task_id": result.task_id,
                "success": result.success,
                "dry_run": result.dry_run,
                "error": result.error,
                "trace": result.output.get("trace"),
                "final_result": result.output.get("final_result"),
            }
            for result in results
        ],
        "trace": next((result.output.get("trace") for result in results if result.output.get("trace")), None),
        "final_result": next(
            (result.output.get("final_result") for result in results if result.output.get("final_result")),
            None,
        ),
        "task_description": description,
        "task_metadata": metadata,
    }


async def _download_media_url_to_path(media_url: str, reel_id: str, *, temp_video_dir: Path) -> Path:
    temp_video_dir.mkdir(parents=True, exist_ok=True)
    target = temp_video_dir / f"{reel_id}.mp4"
    async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
        response = await client.get(media_url)
        response.raise_for_status()
        target.write_bytes(response.content)
    return target


def _build_downloader(backend: str, *, browser_runtime_env: Mapping[str, str] | None = None) -> object:
    if backend == "instaloader":
        return InstagramInstaloaderDownloader(
            config=InstagramInstaloaderDownloader.from_runtime_env(browser_runtime_env)
        )
    if backend == "api":
        return InstagramDownloadAPI()
    msg = f"Unsupported INSTAGRAM_DOWNLOAD_BACKEND={backend!r}"
    raise RuntimeError(msg)


def _instantiate_downloader(backend: str, *, browser_runtime_env: Mapping[str, str] | None = None) -> object:
    if browser_runtime_env is None:
        return _build_downloader(backend)
    try:
        return _build_downloader(backend, browser_runtime_env=browser_runtime_env)
    except TypeError as exc:
        if "browser_runtime_env" not in str(exc):
            raise
        return _build_downloader(backend)


def _configured_download_backends(download_backend: str | None = None) -> list[str]:
    raw = (download_backend or os.getenv("INSTAGRAM_DOWNLOAD_BACKEND", "auto")).strip().lower()
    if not raw or raw == "auto":
        if (os.getenv("INSTAGRAM_DOWNLOADER_API_URL") or "").strip():
            return ["api", "instaloader"]
        return ["instaloader"]

    requested = [part.strip() for part in raw.split(",") if part.strip()]
    backends: list[str] = []
    for backend in requested:
        if backend == "api" and not (os.getenv("INSTAGRAM_DOWNLOADER_API_URL") or "").strip():
            continue
        if backend in {"api", "instaloader"} and backend not in backends:
            backends.append(backend)
    return backends or ["instaloader"]


def _download_attempt_settings() -> tuple[int, float, float]:
    attempts = max(
        1,
        int(os.getenv("INSTAGRAM_DOWNLOAD_MAX_ATTEMPTS_PER_BACKEND", str(DEFAULT_DOWNLOAD_ATTEMPTS_PER_BACKEND))),
    )
    timeout = max(
        30.0,
        float(os.getenv("INSTAGRAM_DOWNLOAD_ATTEMPT_TIMEOUT_SECONDS", str(DEFAULT_DOWNLOAD_ATTEMPT_TIMEOUT_SECONDS))),
    )
    backoff = max(
        0.0,
        float(os.getenv("INSTAGRAM_DOWNLOAD_RETRY_BACKOFF_SECONDS", str(DEFAULT_DOWNLOAD_RETRY_BACKOFF_SECONDS))),
    )
    return attempts, timeout, backoff


async def _resolve_reel_download(
    *,
    reel: ReelSurfaceMetrics,
    backends: list[str],
    downloaders: dict[str, object],
    temp_dir: Path,
) -> tuple[ReelSurfaceMetrics, Path, dict[str, Any]]:
    max_attempts, timeout_seconds, retry_backoff = _download_attempt_settings()
    failures: list[str] = []

    for backend in backends:
        downloader = downloaders[backend]
        for attempt in range(1, max_attempts + 1):
            try:
                if backend == "instaloader":
                    download = await asyncio.wait_for(
                        downloader.download_reel(source_url=reel.source_url, reel_id=reel.reel_id),
                        timeout=timeout_seconds,
                    )
                    temp_path = Path(download.local_video_path)
                    updated_reel = reel.model_copy(
                        update={
                            "video_download_url": download.media_url or reel.video_download_url,
                            "creator_handle": download.creator_handle or reel.creator_handle,
                            "caption_text": download.caption_text or reel.caption_text,
                            "likes": reel.likes if download.likes is None else int(download.likes),
                            "comments": reel.comments if download.comments is None else int(download.comments),
                        }
                    )
                    return (
                        updated_reel,
                        temp_path,
                        {
                            **download.model_dump(mode="json"),
                            "backend": backend,
                            "attempt": attempt,
                        },
                    )

                download = await asyncio.wait_for(
                    downloader.resolve_media_url(source_url=reel.source_url, reel_id=reel.reel_id),
                    timeout=timeout_seconds,
                )
                temp_path = await asyncio.wait_for(
                    _download_media_url_to_path(download.media_url, reel.reel_id, temp_video_dir=temp_dir),
                    timeout=timeout_seconds,
                )
                updated_reel = reel.model_copy(update={"video_download_url": download.media_url})
                return (
                    updated_reel,
                    temp_path,
                    {
                        "reel_id": reel.reel_id,
                        "source_url": reel.source_url,
                        "media_url": download.media_url,
                        "local_video_path": str(temp_path),
                        "backend": backend,
                        "attempt": attempt,
                    },
                )
            except Exception as exc:
                failures.append(f"{backend}[attempt={attempt}]: {type(exc).__name__}: {exc}")
                if attempt < max_attempts and retry_backoff > 0:
                    await asyncio.sleep(retry_backoff * attempt)

    msg = "; ".join(failures) if failures else "No download backend attempts were executed."
    raise RuntimeError(msg)


def _ensure_placeholder_video(*, temp_video_dir: Path, reel_id: str) -> Path:
    temp_video_dir.mkdir(parents=True, exist_ok=True)
    target = temp_video_dir / f"{reel_id}.mp4"
    if not target.exists():
        target.write_bytes(b"")
    return target


async def process_pending_reels_to_structures(
    *,
    store: SQLiteHackathonStore,
    video_understanding: VideoUnderstandingPort,
    dry_run: bool,
    temp_video_dir: str | Path = DEFAULT_TEMP_VIDEO_DIR,
    keep_temp_files: bool = False,
    download_backend: str | None = None,
    browser_runtime_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    temp_dir = Path(temp_video_dir)
    backends = _configured_download_backends(download_backend)
    downloaders = (
        {
            backend: _instantiate_downloader(backend, browser_runtime_env=browser_runtime_env)
            for backend in backends
        }
        if not dry_run
        else {}
    )
    queued_reels = store.list_reel_metrics()
    pending_reels = [reel for reel in queued_reels if reel.reel_id not in _already_processed_reel_ids(store)]
    processed: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for reel in pending_reels:
        temp_path: Path | None = None
        try:
            if dry_run:
                temp_path = _ensure_placeholder_video(temp_video_dir=temp_dir, reel_id=reel.reel_id)
                updated_reel = reel
                download_info = {"mode": "dry_run", "local_video_path": str(temp_path)}
            else:
                updated_reel, temp_path, download_info = await _resolve_reel_download(
                    reel=reel,
                    backends=backends,
                    downloaders=downloaders,
                    temp_dir=temp_dir,
                )

            store.upsert_reel_metrics([updated_reel])
            structure = await video_understanding.analyze_reel_file(str(temp_path), reel_id=reel.reel_id)
            store.save_structure(structure)
            processed.append(
                {
                    "reel_id": reel.reel_id,
                    "source_url": reel.source_url,
                    "temp_video_path": str(temp_path),
                    "structure_record_id": structure.record_id,
                    "download_info": download_info,
                }
            )
        except Exception as exc:
            errors.append({"reel_id": reel.reel_id, "error": f"{type(exc).__name__}: {exc}"})
        finally:
            if temp_path is not None and not keep_temp_files:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    return {
        "queued_reels_count": len(queued_reels),
        "pending_reels_count": len(pending_reels),
        "processed_count": len(processed),
        "errors": errors,
        "stored_structures_count": len(store.list_structures()),
    }


def _run_record_note_lines(*notes: str, errors: list[dict[str, str]] | None = None) -> list[str]:
    out = [note for note in notes if note]
    for item in errors or []:
        out.append(f"{item.get('reel_id', 'unknown')}: {item.get('error', 'unknown_error')}")
    return out


def _build_ready_run_update(
    *,
    base_run: HackathonRunRecord,
    product_title: str,
    product_description: str,
    reels_discovered: int,
    reels_queued: int,
    reels_downloaded: int,
    structures_persisted: int,
    templates_created: int,
    selected_template_id: str,
    product_id: str,
    bundle_id: str,
    artifact_id: str,
    video_path: str | None,
    video_uri: str | None,
    post_draft: InstagramPostDraft,
    notes: list[str],
) -> HackathonRunRecord:
    finished_at = datetime.now(UTC)
    return base_run.model_copy(
        update={
            "status": HackathonRunStatus.READY,
            "product_title": product_title,
            "product_description": product_description,
            "reels_discovered": reels_discovered,
            "reels_queued": reels_queued,
            "reels_downloaded": reels_downloaded,
            "structures_persisted": structures_persisted,
            "templates_created": templates_created,
            "selected_template_id": selected_template_id,
            "product_id": product_id,
            "bundle_id": bundle_id,
            "artifact_id": artifact_id,
            "video_path": video_path,
            "video_uri": video_uri,
            "post_draft": post_draft,
            "caption": post_draft.caption,
            "notes": notes,
            "updated_at": finished_at,
            "finished_at": finished_at,
        }
    )


def _build_failed_run_update(base_run: HackathonRunRecord, exc: Exception) -> HackathonRunRecord:
    finished_at = datetime.now(UTC)
    return base_run.model_copy(
        update={
            "status": HackathonRunStatus.FAILED,
            "error": f"{type(exc).__name__}: {exc}",
            "updated_at": finished_at,
            "finished_at": finished_at,
        }
    )


def _post_job_from_run(record: HackathonRunRecord, *, dry_run: bool) -> PostJob:
    draft = record.post_draft
    if draft is None:
        msg = "Run record is missing an Instagram post draft."
        raise RuntimeError(msg)
    if not record.video_path:
        msg = "Run record is missing a generated video path."
        raise RuntimeError(msg)
    return PostJob(
        job_id=new_id("post"),
        media_path=record.video_path,
        caption=draft.caption,
        hashtags=list(draft.hashtags),
        content_tier=draft.content_tier,
        funnel_position=draft.funnel_position,
        product_name=draft.product_name or record.product_title,
        product_tags=list(draft.product_tags),
        brand_tags=list(draft.brand_tags),
        audio_hook_text=draft.audio_hook_text,
        target_niche=draft.target_niche,
        thumbnail_text=draft.thumbnail_text,
        source_blueprint_id=draft.source_blueprint_id,
        dry_run=dry_run,
    )


def _synthetic_dry_run_post_url(run_id: str) -> str:
    shortcode = run_id.replace("_", "")[-12:] or "dryrunpost"
    return f"https://www.instagram.com/reel/{shortcode}/"


def find_reusable_demo_run(store: SQLiteHackathonStore) -> HackathonRunRecord | None:
    """Pick the best existing run for an instant demo launch."""

    runs = store.list_runs()
    for run in runs:
        if (
            run.status == HackathonRunStatus.READY
            and run.post_draft is not None
            and run.video_path
            and Path(run.video_path).exists()
            and not run.post_url
        ):
            return run
    for run in runs:
        if (
            run.status in {HackathonRunStatus.POSTED, HackathonRunStatus.READY}
            and run.post_draft is not None
            and (run.post_url or run.video_path)
        ):
            return run
    return None


def _find_latest_postable_run(store: SQLiteHackathonStore) -> HackathonRunRecord | None:
    """Return the newest unposted run with a real generated video artifact."""

    for run in store.list_runs():
        if (
            run.status == HackathonRunStatus.READY
            and run.post_draft is not None
            and run.video_path
            and Path(run.video_path).exists()
            and not run.post_url
        ):
            return run
    return None


async def _wait_for_run_ready_to_post(
    *,
    store: SQLiteHackathonStore,
    run_id: str,
    timeout_seconds: float = 180.0,
    poll_interval_seconds: float = 0.5,
) -> HackathonRunRecord:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    latest_run: HackathonRunRecord | None = None
    while asyncio.get_running_loop().time() < deadline:
        latest_run = store.get_run(run_id)
        if latest_run is None:
            msg = f"Pipeline run not found: {run_id}"
            raise RuntimeError(msg)
        if latest_run.status == HackathonRunStatus.FAILED:
            msg = "The selected pipeline run failed and cannot be posted."
            raise RuntimeError(msg)
        if (
            latest_run.status != HackathonRunStatus.RUNNING
            and latest_run.video_path
            and Path(latest_run.video_path).exists()
        ):
            return latest_run
        await asyncio.sleep(poll_interval_seconds)

    msg = f"Timed out waiting for pipeline run to finish video generation before posting: {run_id}"
    raise RuntimeError(msg)


async def _wait_for_structures_available(
    *,
    store: SQLiteHackathonStore,
    timeout_seconds: float = 180.0,
    poll_interval_seconds: float = 0.5,
) -> int:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        count = len(store.list_structures())
        if count > 0:
            return count
        await asyncio.sleep(poll_interval_seconds)
    msg = "Timed out waiting for video structures to become available."
    raise RuntimeError(msg)


async def _wait_for_posted_run(
    *,
    store: SQLiteHackathonStore,
    timeout_seconds: float = 240.0,
    poll_interval_seconds: float = 0.5,
) -> HackathonRunRecord:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        posted_run = next((item for item in store.list_runs() if item.post_url), None)
        if posted_run is not None:
            return posted_run
        await asyncio.sleep(poll_interval_seconds)
    msg = "Timed out waiting for a posted run before comment engagement."
    raise RuntimeError(msg)


def _normalize_run_engagement_persona(
    persona: CommentEngagementPersona | dict[str, Any] | None,
    *,
    run: HackathonRunRecord | None = None,
) -> CommentEngagementPersona:
    fallback_name = ""
    if run is not None:
        fallback_name = run.product_title or (run.post_draft.product_name if run.post_draft is not None else "")
    return normalize_comment_engagement_persona(
        persona,
        fallback_persona_name=fallback_name or "abunnytech",
        fallback_handle="@abunnytech",
    )


def _ensure_posted_content_record(
    *,
    store: SQLiteHackathonStore,
    run: HackathonRunRecord,
    post_url: str,
) -> None:
    if run.post_draft is None:
        return
    posted = store.get_posted_content(post_url)
    if posted is not None:
        return
    store.persist_posted_content(
        PostedContentRecord(
            post_url=post_url,
            job_id=run.run_id,
            caption=run.post_draft.caption,
            hashtags=list(run.post_draft.hashtags),
            content_tier=run.post_draft.content_tier,
            funnel_position=run.post_draft.funnel_position,
            product_name=run.post_draft.product_name or run.product_title,
            product_tag=run.post_draft.product_tags[0] if run.post_draft.product_tags else None,
            brand_tags=list(run.post_draft.brand_tags),
            audio_hook_text=run.post_draft.audio_hook_text,
            target_niche=run.post_draft.target_niche,
            thumbnail_text=run.post_draft.thumbnail_text,
            source_blueprint_id=run.post_draft.source_blueprint_id,
        )
    )


def seed_demo_analytics_for_run(
    *,
    store: SQLiteHackathonStore,
    run: HackathonRunRecord,
    social=None,
) -> DemoAnalyticsSeedResult:
    """Persist deterministic snapshots so demo mode shows immediate analytics."""

    post_url = str(run.post_url or "").strip()
    if not post_url:
        msg = "Run must have a post URL before demo analytics can be seeded."
        raise RuntimeError(msg)

    _ensure_posted_content_record(store=store, run=run, post_url=post_url)
    post_id = str(run.post_id or _extract_instagram_post_id(post_url) or run.run_id)
    end_time = datetime.now(UTC)
    retention_takeaway = (
        "Hook retention is strong through the first second, then the payoff should land earlier "
        "to keep mid-video viewers from dropping."
    )
    adaptation_recommendation = (
        "Keep the opening beat and tighten seconds 3-5 with an earlier payoff, product close-up, "
        "or text pattern interrupt."
    )

    snapshots: list[PostAnalyticsSnapshot] = []
    for scheduled_check, days_after_post, views, likes, comments, shares, saves, follows_gained, trend in (
        DEFAULT_DEMO_ANALYTICS_TIMELINE
    ):
        captured_at = end_time - timedelta(days=max(0, 7 - days_after_post))
        snapshot = PostAnalyticsSnapshot(
            snapshot_id=f"snap_{post_id.lower()}_{scheduled_check}",
            post_id=post_id,
            scheduled_check=scheduled_check,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
            follows_gained=follows_gained,
            retention_curve_pct=dict(DEFAULT_DEMO_ANALYTICS_RETENTION_CURVE_PCT),
            retention_takeaway=retention_takeaway,
            adaptation_recommendation=adaptation_recommendation,
            engagement_trend=trend,
            captured_at=captured_at,
        )
        store.persist_post_analytics(snapshot)
        snapshots.append(snapshot)

    performance_label: str | None = None
    if social is not None and run.selected_template_id:
        template = store.get_template(run.selected_template_id)
        if template is not None:
            updated = social.apply_performance_to_template(template, snapshots[-1])
            performance_label = (
                updated.performance_label.value if updated.performance_label is not None else None
            )

    return DemoAnalyticsSeedResult(
        post_url=post_url,
        post_id=post_id,
        snapshot_ids=[snapshot.snapshot_id for snapshot in snapshots],
        scheduled_checks=[snapshot.scheduled_check or "" for snapshot in snapshots],
        retention_takeaway=retention_takeaway,
        adaptation_recommendation=adaptation_recommendation,
        performance_label=performance_label,
    )


def serialize_post_for_dashboard(
    record: PostedContentRecord,
    *,
    replies: list[Any] | None = None,
) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    reply_models = replies or []
    payload["status"] = "posted" if record.post_url else "pending"
    payload["dry_run"] = False
    payload["recent_replies"] = [
        reply.model_dump(mode="json") if hasattr(reply, "model_dump") else reply for reply in reply_models[:3]
    ]
    payload["engagement_reply_count"] = (
        record.engagement_summary.total_replies_logged if record.engagement_summary is not None else len(reply_models)
    )
    return payload


async def run_dashboard_pipeline(
    *,
    store: SQLiteHackathonStore,
    browser: BrowserAutomationPort,
    video_understanding: VideoUnderstandingPort,
    gemini: GeminiVideoAgentPort,
    veo,
    product_image_path: str,
    avatar_image_path: str,
    dry_run: bool,
    product_title: str | None = None,
    product_description: str | None = None,
    engagement_persona: CommentEngagementPersona | dict[str, Any] | None = None,
    browser_runtime_env: Mapping[str, str] | None = None,
) -> HackathonRunRecord:
    now = datetime.now(UTC)
    run = HackathonRunRecord(
        run_id=new_id("run"),
        status=HackathonRunStatus.RUNNING,
        dry_run=dry_run,
        source_db_path=str(store.db_path),
        avatar_image_path=avatar_image_path,
        product_image_path=product_image_path,
        product_title=product_title or "",
        product_description=product_description or "",
        engagement_persona=_normalize_run_engagement_persona(engagement_persona),
        created_at=now,
        updated_at=now,
    )
    store.save_run(run)

    try:
        discovery = await discover_reels_to_store(
            browser=browser,
            store=store,
            browser_runtime_env=browser_runtime_env,
        )
        processing = await process_pending_reels_to_structures(
            store=store,
            video_understanding=video_understanding,
            dry_run=dry_run,
            browser_runtime_env=browser_runtime_env,
        )
        result = await generate_video_from_best_db_template(
            store,
            gemini=gemini,
            veo=veo,
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
            product_title=product_title,
            product_description=product_description,
        )
        structure = store.get_structure(result.template.structure_record_id)
        metrics = store.get_reel_metric(structure.source_reel_id) if structure is not None else None
        post_draft = await gemini.build_instagram_post_draft(
            result.template,
            result.product,
            bundle=result.bundle,
            artifact=result.artifact,
            structure=structure,
            metrics=metrics,
        )
        run = _build_ready_run_update(
            base_run=run,
            product_title=result.product.title,
            product_description=result.product.notes or product_description or "",
            reels_discovered=int(discovery["parsed_metrics_count"]),
            reels_queued=int(discovery["queued_reels_count"]),
            reels_downloaded=int(processing["processed_count"]),
            structures_persisted=int(processing["processed_count"]),
            templates_created=result.templates_created,
            selected_template_id=result.template.template_id,
            product_id=result.product.product_id,
            bundle_id=result.bundle.bundle_id,
            artifact_id=result.artifact.artifact_id,
            video_path=result.artifact.video_path,
            video_uri=result.artifact.video_uri,
            post_draft=post_draft,
            notes=_run_record_note_lines(
                f"queued_reels={discovery['queued_reels_count']}",
                f"processed_reels={processing['processed_count']}",
                f"template_id={result.template.template_id}",
                errors=processing["errors"],
            ),
        )
    except Exception as exc:
        run = _build_failed_run_update(run, exc)
    store.save_run(run)
    return run


async def generate_video_from_structure_db(
    *,
    store: SQLiteHackathonStore,
    gemini: GeminiVideoAgentPort,
    veo,
    product_image_path: str,
    avatar_image_path: str,
    dry_run: bool,
    product_title: str | None = None,
    product_description: str | None = None,
    engagement_persona: CommentEngagementPersona | dict[str, Any] | None = None,
) -> HackathonRunRecord:
    now = datetime.now(UTC)
    run = HackathonRunRecord(
        run_id=new_id("run"),
        status=HackathonRunStatus.RUNNING,
        dry_run=dry_run,
        source_db_path=str(store.db_path),
        avatar_image_path=avatar_image_path,
        product_image_path=product_image_path,
        product_title=product_title or "",
        product_description=product_description or "",
        reels_discovered=len(store.list_reel_metrics()),
        reels_queued=len(store.list_reel_metrics()),
        reels_downloaded=len(store.list_structures()),
        structures_persisted=len(store.list_structures()),
        engagement_persona=_normalize_run_engagement_persona(engagement_persona),
        created_at=now,
        updated_at=now,
    )
    store.save_run(run)

    try:
        result = await generate_video_from_best_db_template(
            store,
            gemini=gemini,
            veo=veo,
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
            product_title=product_title,
            product_description=product_description,
        )
        structure = store.get_structure(result.template.structure_record_id)
        metrics = store.get_reel_metric(structure.source_reel_id) if structure is not None else None
        post_draft = await gemini.build_instagram_post_draft(
            result.template,
            result.product,
            bundle=result.bundle,
            artifact=result.artifact,
            structure=structure,
            metrics=metrics,
        )
        run = _build_ready_run_update(
            base_run=run,
            product_title=result.product.title,
            product_description=result.product.notes or product_description or "",
            reels_discovered=len(store.list_reel_metrics()),
            reels_queued=len(store.list_reel_metrics()),
            reels_downloaded=len(store.list_structures()),
            structures_persisted=len(store.list_structures()),
            templates_created=result.templates_created,
            selected_template_id=result.template.template_id,
            product_id=result.product.product_id,
            bundle_id=result.bundle.bundle_id,
            artifact_id=result.artifact.artifact_id,
            video_path=result.artifact.video_path,
            video_uri=result.artifact.video_uri,
            post_draft=post_draft,
            notes=_run_record_note_lines(
                "source=video_structure_db",
                f"structures_available={len(store.list_structures())}",
                f"template_id={result.template.template_id}",
                f"templates_created={result.templates_created}",
            ),
        )
    except Exception as exc:
        run = _build_failed_run_update(run, exc)

    store.save_run(run)
    return run


async def run_parallel_demo_mode(
    *,
    store: SQLiteHackathonStore,
    browser: BrowserAutomationPort,
    video_understanding: VideoUnderstandingPort,
    gemini: GeminiVideoAgentPort,
    veo,
    social,
    product_image_path: str,
    avatar_image_path: str,
    dry_run: bool,
    product_title: str | None = None,
    product_description: str | None = None,
    engagement_persona: CommentEngagementPersona | dict[str, Any] | None = None,
    browser_runtime_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    async def discovery_lane() -> dict[str, Any]:
        discovery = await discover_reels_to_store(
            browser=browser,
            store=store,
            browser_runtime_env=browser_runtime_env,
        )
        processing = await process_pending_reels_to_structures(
            store=store,
            video_understanding=video_understanding,
            dry_run=dry_run,
            browser_runtime_env=browser_runtime_env,
        )
        return {
            "lane": "reel_discovery_to_video_structure",
            "status": "completed",
            "queued_reels_count": int(discovery["queued_reels_count"]),
            "processed_count": int(processing["processed_count"]),
            "stored_structures_count": int(processing["stored_structures_count"]),
            "errors": list(processing["errors"]),
        }

    async def generation_lane() -> dict[str, Any]:
        await _wait_for_structures_available(store=store)
        generated_run = await generate_video_from_structure_db(
            store=store,
            gemini=gemini,
            veo=veo,
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
            dry_run=dry_run,
            product_title=product_title,
            product_description=product_description,
            engagement_persona=engagement_persona,
        )
        posted_run, publish_output = await post_latest_run(
            store=store,
            social=social,
            dry_run=dry_run,
            run_id=generated_run.run_id,
        )
        return {
            "lane": "video_structure_to_video_gen_and_instagram_posting",
            "status": "completed",
            "run_id": posted_run.run_id,
            "post_url": posted_run.post_url,
            "selected_template_id": posted_run.selected_template_id,
            "publish_output": publish_output,
        }

    async def engagement_lane() -> dict[str, Any]:
        posted_run = await _wait_for_posted_run(store=store)
        updated_run, summary = await engage_latest_posted_run(
            store=store,
            social=social,
            dry_run=dry_run,
            run_id=posted_run.run_id,
        )
        return {
            "lane": "comment_engagement",
            "status": "completed",
            "run_id": updated_run.run_id,
            "engagement_status": summary.status.value,
            "replies_logged": summary.total_replies_logged,
        }

    tasks = {
        "reel_discovery_to_video_structure": asyncio.create_task(discovery_lane()),
        "video_structure_to_video_gen_and_instagram_posting": asyncio.create_task(generation_lane()),
        "comment_engagement": asyncio.create_task(engagement_lane()),
    }

    results: dict[str, Any] = {}
    for lane_name, task in tasks.items():
        try:
            results[lane_name] = await task
        except Exception as exc:
            results[lane_name] = {
                "lane": lane_name,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
    return results


async def post_latest_run(
    *,
    store: SQLiteHackathonStore,
    social,
    dry_run: bool,
    run_id: str | None = None,
) -> tuple[HackathonRunRecord, dict[str, Any]]:
    run = store.get_run(run_id) if run_id else _find_latest_postable_run(store)
    if run is None:
        msg = (
            "No postable pipeline run exists yet. Generate a video successfully before posting."
        )
        raise RuntimeError(msg)
    run = await _wait_for_run_ready_to_post(store=store, run_id=run.run_id)
    job = _post_job_from_run(run, dry_run=dry_run)
    result = await social.publish_reel(job)
    output = dict(result.output)
    post_url = str(output.get("post_url") or "")
    if dry_run and not post_url:
        post_url = _synthetic_dry_run_post_url(run.run_id)
        output["post_url"] = post_url
    if post_url:
        _ensure_posted_content_record(
            store=store,
            run=run,
            post_url=post_url,
        )
    post_id = str(output.get("post_id") or _extract_instagram_post_id(post_url)) if post_url else None
    engagement_summary: CommentEngagementSummary | None = None
    if post_url and not dry_run:
        engagement_summary = await social.engage_post_comments(
            post_url,
            persona=run.engagement_persona,
            dry_run=False,
            run_id=run.run_id,
        )
        output["engagement_summary"] = engagement_summary.model_dump(mode="json")
    now = datetime.now(UTC)
    updated = run.model_copy(
        update={
            "status": HackathonRunStatus.POSTED if post_url else run.status,
            "post_url": post_url or run.post_url,
            "post_id": post_id or run.post_id,
            "engagement_summary": engagement_summary or run.engagement_summary,
            "updated_at": now,
            "finished_at": now,
            "notes": [
                *run.notes,
                "dry_run_post" if dry_run else "live_post",
            ],
        }
    )
    store.save_run(updated)
    return updated, output


async def engage_latest_posted_run(
    *,
    store: SQLiteHackathonStore,
    social,
    dry_run: bool,
    run_id: str | None = None,
) -> tuple[HackathonRunRecord, CommentEngagementSummary]:
    run = store.get_run(run_id) if run_id else store.latest_run()
    if run is None:
        msg = "No pipeline run exists yet."
        raise RuntimeError(msg)
    post_url = str(run.post_url or "")
    if not post_url:
        msg = "The selected pipeline run has not been posted yet."
        raise RuntimeError(msg)

    if store.get_posted_content(post_url) is None:
        _ensure_posted_content_record(
            store=store,
            run=run,
            post_url=post_url,
        )

    summary = await social.engage_post_comments(
        post_url,
        persona=run.engagement_persona,
        dry_run=dry_run,
        run_id=run.run_id,
    )
    now = datetime.now(UTC)
    updated = run.model_copy(
        update={
            "engagement_summary": summary,
            "updated_at": now,
            "finished_at": now,
            "notes": [
                *run.notes,
                "dry_run_engagement" if dry_run else "live_engagement",
            ],
        }
    )
    store.save_run(updated)
    return updated, summary


def serialize_run_for_dashboard(
    record: HackathonRunRecord | None,
) -> dict[str, Any] | None:
    if record is None:
        return None
    payload = record.model_dump(mode="json")
    payload["is_post_ready"] = bool(record.post_draft and record.video_path)
    payload["engagement_reply_count"] = (
        record.engagement_summary.total_replies_logged if record.engagement_summary is not None else 0
    )
    return payload
