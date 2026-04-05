from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from hackathon_pipelines import build_runtime_stack
from hackathon_pipelines.adapters.instagram_instaloader import InstagramInstaloaderDownload
from hackathon_pipelines.contracts import (
    CommentEngagementPersona,
    CommentEngagementStatus,
    CommentEngagementSummary,
    HackathonRunRecord,
    HackathonRunStatus,
    InstagramPostDraft,
    ReelSurfaceMetrics,
    VideoStructureRecord,
)
from hackathon_pipelines.dashboard_workflow import (
    _build_dashboard_discovery_task,
    discover_reels_to_store,
    engage_latest_posted_run,
    find_reusable_demo_run,
    generate_video_from_structure_db,
    post_latest_run,
    process_pending_reels_to_structures,
    run_dashboard_pipeline,
    run_parallel_demo_mode,
    seed_demo_analytics_for_run,
)
from hackathon_pipelines.pipelines import reel_discovery as reel_discovery_module
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore


@pytest.mark.asyncio
async def test_run_dashboard_pipeline_persists_ready_run(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    run = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Demo Camera",
        product_description="Compact creator camera for storefront demos.",
    )

    assert run.status == HackathonRunStatus.READY
    assert run.post_draft is not None
    assert run.caption
    assert run.video_path is not None
    assert Path(run.video_path).exists()
    assert stack.store.latest_run() is not None
    assert stack.store.latest_run().run_id == run.run_id


@pytest.mark.asyncio
async def test_post_latest_run_updates_record_in_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    run = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Demo Camera",
        product_description="Compact creator camera for storefront demos.",
    )

    posted_run, output = await post_latest_run(
        store=stack.store,
        social=stack.social,
        dry_run=True,
        run_id=run.run_id,
    )

    assert posted_run.status == HackathonRunStatus.POSTED
    assert posted_run.post_url is not None
    assert posted_run.post_id is not None
    assert output["post_url"] == posted_run.post_url


@pytest.mark.asyncio
async def test_post_latest_run_skips_newer_failed_run_and_posts_latest_ready_video(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    ready_run = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Ready Product",
        product_description="This run should be posted.",
    )

    now = datetime.now(UTC)
    failed_run = HackathonRunRecord(
        run_id="run_failed_newer",
        status=HackathonRunStatus.FAILED,
        dry_run=False,
        source_db_path=str(db_path),
        product_title="Failed Product",
        product_description="This newer run has no video.",
        error="quota exhausted",
        created_at=now,
        updated_at=now,
        finished_at=now,
    )
    stack.store.save_run(failed_run)

    posted_run, output = await post_latest_run(
        store=stack.store,
        social=stack.social,
        dry_run=True,
    )

    assert posted_run.run_id == ready_run.run_id
    assert posted_run.status == HackathonRunStatus.POSTED
    assert output["post_url"] == posted_run.post_url


@pytest.mark.asyncio
async def test_generate_video_from_structure_db_creates_ready_run(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    seeded_run = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Seed Product",
        product_description="Seed description",
    )

    generated_run = await generate_video_from_structure_db(
        store=stack.store,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="DB Product",
        product_description="DB description",
        engagement_persona=CommentEngagementPersona(
            persona_name="TechTok Sarah",
            instagram_handle="@techtok.sarah",
        ),
    )

    assert seeded_run.status == HackathonRunStatus.READY
    assert generated_run.status == HackathonRunStatus.READY
    assert generated_run.run_id != seeded_run.run_id
    assert generated_run.video_path
    assert generated_run.selected_template_id is not None
    assert generated_run.post_draft is not None
    assert "source=video_structure_db" in generated_run.notes


@pytest.mark.asyncio
async def test_run_parallel_demo_mode_completes_three_lanes_in_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    result = await run_parallel_demo_mode(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        social=stack.social,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Demo Product",
        product_description="Demo description",
        engagement_persona=CommentEngagementPersona(
            persona_name="TechTok Sarah",
            instagram_handle="@techtok.sarah",
        ),
    )

    assert result["reel_discovery_to_video_structure"]["status"] == "completed"
    assert result["video_structure_to_video_gen_and_instagram_posting"]["status"] == "completed"
    assert result["comment_engagement"]["status"] == "completed"


@pytest.mark.asyncio
async def test_find_reusable_demo_run_prefers_latest_ready_unposted_run(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    first = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Demo Camera",
        product_description="Compact creator camera for storefront demos.",
    )
    await post_latest_run(
        store=stack.store,
        social=stack.social,
        dry_run=True,
        run_id=first.run_id,
    )
    second = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Demo Camera 2",
        product_description="Fresh background-ready run.",
    )

    selected = find_reusable_demo_run(stack.store)

    assert selected is not None
    assert selected.run_id == second.run_id


@pytest.mark.asyncio
async def test_seed_demo_analytics_for_run_persists_snapshots_and_updates_template(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    run = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Demo Camera",
        product_description="Compact creator camera for storefront demos.",
    )
    posted_run, _ = await post_latest_run(
        store=stack.store,
        social=stack.social,
        dry_run=True,
        run_id=run.run_id,
    )

    result = seed_demo_analytics_for_run(
        store=stack.store,
        run=posted_run,
        social=stack.social,
    )

    snapshots = stack.store.list_snapshots()
    updated_template = stack.store.get_template(posted_run.selected_template_id or "")

    assert result.post_url == posted_run.post_url
    assert result.scheduled_checks == ["day_1", "day_3", "week_1"]
    assert len(result.snapshot_ids) == 3
    assert len(snapshots) == 3
    assert updated_template is not None
    assert updated_template.performance_label is not None


@pytest.mark.asyncio
async def test_post_latest_run_auto_engages_live_post(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    run = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Demo Camera",
        product_description="Compact creator camera for storefront demos.",
        engagement_persona=CommentEngagementPersona(
            persona_name="TechTok Sarah",
            instagram_handle="@techtok.sarah",
        ),
    )

    class FakeSocial:
        async def publish_reel(self, job):
            from browser_runtime.types import AgentResult, ProviderType

            return AgentResult(
                task_id="publish_live",
                success=True,
                provider=ProviderType.MOCK,
                output={"post_url": "https://www.instagram.com/reel/LIVE123/"},
            )

        async def engage_post_comments(self, post_url: str, *, persona, dry_run: bool, run_id: str | None = None):
            assert post_url.endswith("/LIVE123/")
            assert dry_run is False
            assert run_id == run.run_id
            assert persona is not None
            return CommentEngagementSummary(
                status=CommentEngagementStatus.REPLIED,
                total_replies_logged=2,
                replies_posted_this_run=2,
            )

    posted_run, output = await post_latest_run(
        store=stack.store,
        social=FakeSocial(),
        dry_run=False,
        run_id=run.run_id,
    )

    assert posted_run.status == HackathonRunStatus.POSTED
    assert posted_run.engagement_summary is not None
    assert posted_run.engagement_summary.status == CommentEngagementStatus.REPLIED
    assert output["engagement_summary"]["status"] == CommentEngagementStatus.REPLIED.value


@pytest.mark.asyncio
async def test_post_latest_run_waits_for_ready_video_before_publishing(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    store = SQLiteHackathonStore(db_path)
    video_path = tmp_path / "generated.mp4"
    run = HackathonRunRecord(
        run_id="run_waiting",
        status=HackathonRunStatus.RUNNING,
        dry_run=False,
        source_db_path=str(db_path),
        video_path=str(video_path),
        post_draft=InstagramPostDraft(caption="launch post"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    store.save_run(run)

    class FakeSocial:
        def __init__(self) -> None:
            self.published = False

        async def publish_reel(self, job):
            from browser_runtime.types import AgentResult, ProviderType

            assert video_path.exists()
            self.published = True
            return AgentResult(
                task_id="publish_after_wait",
                success=True,
                provider=ProviderType.MOCK,
                output={"post_url": "https://www.instagram.com/reel/WAIT123/"},
            )

    async def mark_run_ready() -> None:
        await asyncio.sleep(0.05)
        video_path.write_bytes(b"mp4")
        store.save_run(
            run.model_copy(
                update={
                    "status": HackathonRunStatus.READY,
                    "updated_at": datetime.now(UTC),
                    "finished_at": datetime.now(UTC),
                }
            )
        )

    social = FakeSocial()
    ready_task = asyncio.create_task(mark_run_ready())
    posted_run, output = await post_latest_run(
        store=store,
        social=social,
        dry_run=True,
        run_id=run.run_id,
    )
    await ready_task

    assert social.published is True
    assert posted_run.status == HackathonRunStatus.POSTED
    assert output["post_url"] == posted_run.post_url


@pytest.mark.asyncio
async def test_engage_latest_posted_run_updates_run_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    product = tmp_path / "product.jpg"
    avatar = tmp_path / "avatar.jpg"
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)

    run = await run_dashboard_pipeline(
        store=stack.store,
        browser=stack.browser,
        video_understanding=stack.video_understanding,
        gemini=stack.gemini,
        veo=stack.veo,
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        dry_run=True,
        product_title="Demo Camera",
        product_description="Compact creator camera for storefront demos.",
    )
    run = run.model_copy(
        update={
            "status": HackathonRunStatus.POSTED,
            "post_url": "https://www.instagram.com/reel/MANUAL123/",
        }
    )
    stack.store.save_run(run)

    class FakeSocial:
        async def engage_post_comments(self, post_url: str, *, persona, dry_run: bool, run_id: str | None = None):
            assert post_url.endswith("/MANUAL123/")
            return CommentEngagementSummary(
                status=CommentEngagementStatus.NO_ACTION_NEEDED,
                total_replies_logged=0,
                replies_posted_this_run=0,
                last_reason="no comments needed a response",
            )

    updated_run, summary = await engage_latest_posted_run(
        store=stack.store,
        social=FakeSocial(),
        dry_run=False,
        run_id=run.run_id,
    )

    assert updated_run.engagement_summary is not None
    assert updated_run.engagement_summary.status == CommentEngagementStatus.NO_ACTION_NEEDED
    assert summary.last_reason == "no comments needed a response"


@pytest.mark.asyncio
async def test_process_pending_reels_falls_back_to_secondary_downloader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    store = SQLiteHackathonStore(db_path)
    store.upsert_reel_metrics(
        [
            ReelSurfaceMetrics(
                reel_id="reel_1",
                source_url="https://www.instagram.com/reels/ABC123/",
                likes=1000,
                comments=100,
                is_ugc_candidate=True,
            )
        ]
    )

    class FakeVideoUnderstanding:
        async def analyze_reel_file(self, media_path: str, *, reel_id: str) -> VideoStructureRecord:
            assert Path(media_path).exists()
            return VideoStructureRecord(
                record_id="rec_1",
                source_reel_id=reel_id,
                raw_analysis_text="ok",
            )

    class FailingAPI:
        async def resolve_media_url(self, *, source_url: str, reel_id: str):
            raise RuntimeError("api_down")

    local_video = tmp_path / "ABC123.mp4"
    local_video.write_bytes(b"mp4")

    class WorkingInstaloader:
        async def download_reel(self, *, source_url: str, reel_id: str) -> InstagramInstaloaderDownload:
            return InstagramInstaloaderDownload(
                reel_id=reel_id,
                source_url=source_url,
                shortcode="ABC123",
                local_video_path=str(local_video),
                media_url="https://cdn.example.com/ABC123.mp4",
                creator_handle="creator_test",
                caption_text="Great demo",
                likes=2222,
                comments=88,
            )

    monkeypatch.setattr(
        "hackathon_pipelines.dashboard_workflow._configured_download_backends",
        lambda _backend=None: ["api", "instaloader"],
    )
    monkeypatch.setattr(
        "hackathon_pipelines.dashboard_workflow._build_downloader",
        lambda backend: FailingAPI() if backend == "api" else WorkingInstaloader(),
    )
    monkeypatch.setenv("INSTAGRAM_DOWNLOAD_MAX_ATTEMPTS_PER_BACKEND", "1")
    monkeypatch.setenv("INSTAGRAM_DOWNLOAD_RETRY_BACKOFF_SECONDS", "0")

    result = await process_pending_reels_to_structures(
        store=store,
        video_understanding=FakeVideoUnderstanding(),
        dry_run=False,
        keep_temp_files=True,
    )

    updated = store.get_reel_metric("reel_1")
    assert result["processed_count"] == 1
    assert result["errors"] == []
    assert updated is not None
    assert updated.video_download_url == "https://cdn.example.com/ABC123.mp4"
    assert updated.creator_handle == "creator_test"
    assert len(store.list_structures()) == 1


@pytest.mark.asyncio
async def test_process_pending_reels_retries_same_backend_before_failing_over(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    store = SQLiteHackathonStore(db_path)
    store.upsert_reel_metrics(
        [
            ReelSurfaceMetrics(
                reel_id="reel_2",
                source_url="https://www.instagram.com/reels/XYZ789/",
                likes=1200,
                comments=120,
                is_ugc_candidate=True,
            )
        ]
    )

    class FakeVideoUnderstanding:
        async def analyze_reel_file(self, media_path: str, *, reel_id: str) -> VideoStructureRecord:
            assert Path(media_path).exists()
            return VideoStructureRecord(
                record_id="rec_2",
                source_reel_id=reel_id,
                raw_analysis_text="ok",
            )

    local_video = tmp_path / "XYZ789.mp4"
    local_video.write_bytes(b"mp4")
    attempts = {"instaloader": 0}

    class FlakyInstaloader:
        async def download_reel(self, *, source_url: str, reel_id: str) -> InstagramInstaloaderDownload:
            attempts["instaloader"] += 1
            if attempts["instaloader"] == 1:
                raise RuntimeError("temporary_403")
            return InstagramInstaloaderDownload(
                reel_id=reel_id,
                source_url=source_url,
                shortcode="XYZ789",
                local_video_path=str(local_video),
                media_url="https://cdn.example.com/XYZ789.mp4",
            )

    monkeypatch.setattr(
        "hackathon_pipelines.dashboard_workflow._configured_download_backends",
        lambda _backend=None: ["instaloader"],
    )
    monkeypatch.setattr(
        "hackathon_pipelines.dashboard_workflow._build_downloader",
        lambda backend: FlakyInstaloader(),
    )
    monkeypatch.setenv("INSTAGRAM_DOWNLOAD_MAX_ATTEMPTS_PER_BACKEND", "2")
    monkeypatch.setenv("INSTAGRAM_DOWNLOAD_RETRY_BACKOFF_SECONDS", "0")

    result = await process_pending_reels_to_structures(
        store=store,
        video_understanding=FakeVideoUnderstanding(),
        dry_run=False,
        keep_temp_files=True,
    )

    assert attempts["instaloader"] == 2
    assert result["processed_count"] == 1
    assert result["errors"] == []
    assert len(store.list_structures()) == 1


@pytest.mark.asyncio
async def test_process_pending_reels_passes_browser_runtime_env_to_instaloader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    store = SQLiteHackathonStore(db_path)
    store.upsert_reel_metrics(
        [
            ReelSurfaceMetrics(
                reel_id="reel_3",
                source_url="https://www.instagram.com/reels/ENV123/",
                likes=1200,
                comments=120,
                is_ugc_candidate=True,
            )
        ]
    )
    captured: dict[str, object] = {}

    class FakeVideoUnderstanding:
        async def analyze_reel_file(self, media_path: str, *, reel_id: str) -> VideoStructureRecord:
            return VideoStructureRecord(
                record_id="rec_3",
                source_reel_id=reel_id,
                raw_analysis_text="ok",
            )

    local_video = tmp_path / "ENV123.mp4"
    local_video.write_bytes(b"mp4")

    class WorkingInstaloader:
        async def download_reel(self, *, source_url: str, reel_id: str) -> InstagramInstaloaderDownload:
            return InstagramInstaloaderDownload(
                reel_id=reel_id,
                source_url=source_url,
                shortcode="ENV123",
                local_video_path=str(local_video),
                media_url="https://cdn.example.com/ENV123.mp4",
            )

    monkeypatch.setattr(
        "hackathon_pipelines.dashboard_workflow._configured_download_backends",
        lambda _backend=None: ["instaloader"],
    )

    def fake_build_downloader(backend: str, *, browser_runtime_env=None):
        captured["backend"] = backend
        captured["browser_runtime_env"] = browser_runtime_env
        return WorkingInstaloader()

    monkeypatch.setattr(
        "hackathon_pipelines.dashboard_workflow._build_downloader",
        fake_build_downloader,
    )

    result = await process_pending_reels_to_structures(
        store=store,
        video_understanding=FakeVideoUnderstanding(),
        dry_run=False,
        keep_temp_files=True,
        browser_runtime_env={
            "CHROME_USER_DATA_DIR": "/tmp/dashboard_clone/Profile_9_root",
            "CHROME_PROFILE_DIRECTORY": "Profile 9",
        },
    )

    assert result["processed_count"] == 1
    assert captured["backend"] == "instaloader"
    assert captured["browser_runtime_env"] == {
        "CHROME_USER_DATA_DIR": "/tmp/dashboard_clone/Profile_9_root",
        "CHROME_PROFILE_DIRECTORY": "Profile 9",
    }


def test_build_dashboard_discovery_task_stays_on_instagram_and_disables_browser_downloads() -> None:
    description, metadata = _build_dashboard_discovery_task()

    assert "https://www.instagram.com/reels/" in description
    assert "NEVER use search engines" in description
    assert "NEVER open downloader sites" in description
    assert "Downloading happens later through the API/downloader pipeline outside the browser." in description
    assert metadata["browser_use_output_model_schema"] is reel_discovery_module.BrowserUseDiscoveredReels
    assert "DuckDuckGo" in metadata["browser_use"]["extend_system_message"]
    assert "do not visit downloader sites" in metadata["browser_use"]["extend_system_message"]


@pytest.mark.asyncio
async def test_discover_reels_to_store_opens_instagram_reels_url(tmp_path: Path) -> None:
    store = SQLiteHackathonStore(tmp_path / "hackathon.sqlite3")
    captured_tasks: list[object] = []

    class FakeBrowser:
        async def run_task(self, task):
            captured_tasks.append(task)
            return reel_discovery_module.AgentResult(
                task_id=f"discover_{len(captured_tasks)}",
                success=True,
                provider=reel_discovery_module.ProviderType.BROWSER_USE,
                output={"reels": []},
                dry_run=True,
            )

    result = await discover_reels_to_store(browser=FakeBrowser(), store=store)

    assert result["browser_success"] is True
    assert result["agent_count"] == 3
    assert result["successful_agent_runs"] == 3
    assert result["failed_agent_runs"] == 0
    assert len(captured_tasks) == 3
    assert all(task.url == reel_discovery_module.INSTAGRAM_REELS_FEED_URL for task in captured_tasks)
    assert all("NEVER search for 'instagram reel downloader'" in str(task.description) for task in captured_tasks)
    assert all(task.metadata["discovery_agent_count"] == 3 for task in captured_tasks)
    assert [task.metadata["discovery_agent_index"] for task in captured_tasks] == [0, 1, 2]


@pytest.mark.asyncio
async def test_discover_reels_to_store_merges_duplicate_results_across_workers(tmp_path: Path) -> None:
    store = SQLiteHackathonStore(tmp_path / "hackathon.sqlite3")
    payloads = [
        [
            {
                "reel_id": "AAA111",
                "source_url": "https://www.instagram.com/reel/AAA111/",
                "likes": 1200,
                "comments": 80,
                "views": 25000,
                "creator_handle": "creator.alpha",
                "is_ugc_candidate": True,
                "ugc_reason": "product demo",
            }
        ],
        [
            {
                "reel_id": "AAA111",
                "source_url": "https://www.instagram.com/reel/AAA111/",
                "likes": 1800,
                "comments": 95,
                "views": 41000,
                "caption_text": "better caption",
                "is_ugc_candidate": True,
            }
        ],
        [
            {
                "reel_id": "BBB222",
                "source_url": "https://www.instagram.com/reel/BBB222/",
                "likes": 900,
                "comments": 35,
                "views": 16000,
                "creator_handle": "creator.beta",
                "is_ugc_candidate": True,
                "ugc_reason": "testimonial",
            }
        ],
    ]

    class FakeBrowser:
        def __init__(self) -> None:
            self.calls = 0

        async def run_task(self, task):
            self.calls += 1
            return reel_discovery_module.AgentResult(
                task_id=f"discover_{self.calls}",
                success=True,
                provider=reel_discovery_module.ProviderType.BROWSER_USE,
                output={"reels": payloads[self.calls - 1]},
                dry_run=False,
            )

    browser = FakeBrowser()
    result = await discover_reels_to_store(browser=browser, store=store)

    assert browser.calls == 3
    assert result["parsed_metrics_count"] == 2
    assert result["queued_reels_count"] == 2
    stored = {row.reel_id: row for row in store.list_reel_metrics()}
    assert set(stored) == {"AAA111", "BBB222"}
    assert stored["AAA111"].likes == 1800
    assert stored["AAA111"].comments == 95
    assert stored["AAA111"].views == 41000
    assert stored["AAA111"].caption_text == "better caption"


@pytest.mark.asyncio
async def test_discover_reels_to_store_passes_browser_runtime_env_to_parallel_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteHackathonStore(tmp_path / "hackathon.sqlite3")
    captured: dict[str, object] = {}

    async def fake_run_parallel_reel_discovery(**kwargs):
        captured.update(kwargs)
        return [], [
            reel_discovery_module.AgentResult(
                task_id="discover_dry",
                success=True,
                provider=reel_discovery_module.ProviderType.BROWSER_USE,
                output={},
                dry_run=True,
            )
        ]

    monkeypatch.setattr(
        "hackathon_pipelines.dashboard_workflow.run_parallel_reel_discovery",
        fake_run_parallel_reel_discovery,
    )

    result = await discover_reels_to_store(
        browser=object(),
        store=store,
        browser_runtime_env={
            "BROWSER_USE_CDP_URL": "http://127.0.0.1:9222",
            "CHROME_USER_DATA_DIR": "/tmp/profile-clone",
            "CHROME_PROFILE_DIRECTORY": "Profile 9",
        },
    )

    assert result["browser_success"] is True
    assert captured["browser_runtime_env"] == {
        "BROWSER_USE_CDP_URL": "http://127.0.0.1:9222",
        "CHROME_USER_DATA_DIR": "/tmp/profile-clone",
        "CHROME_PROFILE_DIRECTORY": "Profile 9",
    }
