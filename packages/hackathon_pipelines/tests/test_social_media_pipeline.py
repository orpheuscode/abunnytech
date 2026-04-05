from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from browser_runtime.types import AgentResult, ProviderType

from hackathon_pipelines.contracts import (
    CommentEngagementPersona,
    CommentEngagementStatus,
    CommentReplyRecord,
    PostedContentRecord,
    PostJob,
)
from hackathon_pipelines.pipelines import social_media as social_media_module
from hackathon_pipelines.pipelines.social_media import SocialMediaPipeline
from hackathon_pipelines.stores import MemoryAnalyticsSink, MemoryPostedContentSink, MemoryTemplateStore


class _CapturingBrowser:
    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.tasks = []

    async def run_task(self, task):
        self.tasks.append(task)
        return self.result


@pytest.mark.asyncio
async def test_publish_reel_uses_teammate_prompt_and_browser_use_metadata(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "generated.mp4"
    video_path.write_bytes(b"mp4")

    monkeypatch.setattr(
        social_media_module,
        "_prepare_instagram_reel_upload",
        lambda _video_path: str(video_path.resolve()),
    )
    monkeypatch.setattr(
        social_media_module,
        "_maybe_generate_thumbnail",
        lambda _video_path, _text: str(tmp_path / "thumb.jpg"),
    )

    browser = _CapturingBrowser(
        AgentResult(
            task_id="task_1",
            success=True,
            provider=ProviderType.MOCK,
            output={"post_url": "https://www.instagram.com/reel/ABC123/"},
        )
    )
    pipeline = SocialMediaPipeline(
        browser=browser,
        analytics_sink=MemoryAnalyticsSink(),
        posted_content_sink=MemoryPostedContentSink(),
        templates=MemoryTemplateStore(),
    )

    result = await pipeline.publish_reel(
        PostJob(
            job_id="job_1",
            media_path=str(video_path),
            caption="Line one\nLine two",
            brand_tags=["@brand"],
            product_name="Demo Product",
            audio_hook_text="Hook text",
            target_niche="beauty",
            funnel_position="MOF",
            content_tier="MOF",
            thumbnail_text="2 WEEK RESULTS",
            source_blueprint_id="bp_123",
        )
    )

    assert result.output["post_id"] == "ABC123"
    task = browser.tasks[0]
    assert "You are posting a reel to Instagram. You are already logged in." in task.description
    assert "filepath:" in task.description
    assert "Line one [NEWLINE] Line two" in task.description
    assert "Call save_post IMMEDIATELY after the post goes live" in task.description
    assert task.metadata["browser_use"]["use_vision"] is True
    assert task.metadata["browser_use"]["vision_detail_level"] == "high"
    assert task.metadata["browser_use"]["directly_open_url"] is False
    assert task.metadata["browser_use_browser"] is None
    assert task.metadata["browser_use_agent_kwargs"]["available_file_paths"] == [
        str(video_path.resolve()),
        str(tmp_path / "thumb.jpg"),
    ]


@pytest.mark.asyncio
async def test_publish_reel_requests_dedicated_local_browser_window_when_runtime_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    video_path = tmp_path / "generated.mp4"
    video_path.write_bytes(b"mp4")

    monkeypatch.setattr(
        social_media_module,
        "_prepare_instagram_reel_upload",
        lambda _video_path: str(video_path.resolve()),
    )
    monkeypatch.setattr(
        social_media_module,
        "_maybe_generate_thumbnail",
        lambda _video_path, _text: None,
    )

    browser = _CapturingBrowser(
        AgentResult(
            task_id="task_window_1",
            success=True,
            provider=ProviderType.MOCK,
            output={"post_url": "https://www.instagram.com/reel/WIN123/"},
        )
    )
    pipeline = SocialMediaPipeline(
        browser=browser,
        analytics_sink=MemoryAnalyticsSink(),
        posted_content_sink=MemoryPostedContentSink(),
        templates=MemoryTemplateStore(),
        browser_runtime_env={
            "BROWSER_USE_CDP_URL": "http://localhost:9222",
            "CHROME_EXECUTABLE_PATH": "/usr/bin/google-chrome",
            "CHROME_USER_DATA_DIR": "/tmp/browser-profile-clone",
            "CHROME_PROFILE_DIRECTORY": "Profile 9",
        },
    )

    await pipeline.publish_reel(
        PostJob(
            job_id="job_window_1",
            media_path=str(video_path),
            caption="Caption",
            product_name="Demo Product",
            source_blueprint_id="bp_window",
        )
    )

    task = browser.tasks[0]
    assert task.metadata["browser_use_browser"] == {
        "cdp_url": None,
        "headless": False,
        "keep_alive": False,
        "isolate_local_browser_profile": True,
        "executable_path": "/usr/bin/google-chrome",
        "user_data_dir": "/tmp/browser-profile-clone",
        "profile_directory": "Profile 9",
        "extra_kwargs": {"enable_default_extensions": False},
    }


@pytest.mark.asyncio
async def test_publish_reel_normalizes_relative_thumbnail_path(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "generated.mp4"
    video_path.write_bytes(b"mp4")
    thumb_rel = Path("output/hackathon_thumbnails/test-thumb.jpg")
    thumb_rel.parent.mkdir(parents=True, exist_ok=True)
    thumb_rel.write_bytes(b"jpg")

    monkeypatch.setattr(
        social_media_module,
        "_prepare_instagram_reel_upload",
        lambda _video_path: str(video_path.resolve()),
    )
    monkeypatch.setattr(
        social_media_module,
        "_maybe_generate_thumbnail",
        lambda _video_path, _text: str(thumb_rel),
    )

    browser = _CapturingBrowser(
        AgentResult(
            task_id="task_2",
            success=True,
            provider=ProviderType.MOCK,
            output={"post_url": "https://www.instagram.com/reel/XYZ789/"},
        )
    )
    pipeline = SocialMediaPipeline(
        browser=browser,
        analytics_sink=MemoryAnalyticsSink(),
        posted_content_sink=MemoryPostedContentSink(),
        templates=MemoryTemplateStore(),
    )

    await pipeline.publish_reel(
        PostJob(
            job_id="job_2",
            media_path=str(video_path),
            caption="Caption",
            product_name="Demo Product",
            thumbnail_text="TOP PICK",
            source_blueprint_id="bp_456",
        )
    )

    task = browser.tasks[0]
    resolved_thumb = str(thumb_rel.resolve())
    assert resolved_thumb in task.description
    assert task.metadata["browser_use_agent_kwargs"]["available_file_paths"] == [
        str(video_path.resolve()),
        resolved_thumb,
    ]


@pytest.mark.asyncio
async def test_publish_reel_uses_prepared_instagram_upload_path(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "generated.mp4"
    prepared_path = tmp_path / "prepared.instagram.mp4"
    video_path.write_bytes(b"mp4")
    prepared_path.write_bytes(b"prepared")

    monkeypatch.setattr(
        social_media_module,
        "_prepare_instagram_reel_upload",
        lambda _video_path: str(prepared_path.resolve()),
    )
    monkeypatch.setattr(
        social_media_module,
        "_maybe_generate_thumbnail",
        lambda _video_path, _text: None,
    )

    browser = _CapturingBrowser(
        AgentResult(
            task_id="task_3",
            success=True,
            provider=ProviderType.MOCK,
            output={"post_url": "https://www.instagram.com/reel/PREP123/"},
        )
    )
    pipeline = SocialMediaPipeline(
        browser=browser,
        analytics_sink=MemoryAnalyticsSink(),
        posted_content_sink=MemoryPostedContentSink(),
        templates=MemoryTemplateStore(),
    )

    await pipeline.publish_reel(
        PostJob(
            job_id="job_3",
            media_path=str(video_path),
            caption="Caption",
            product_name="Demo Product",
            source_blueprint_id="bp_789",
        )
    )

    task = browser.tasks[0]
    assert str(prepared_path.resolve()) in task.description
    assert task.metadata["browser_use_agent_kwargs"]["available_file_paths"] == [
        str(prepared_path.resolve()),
    ]


def test_build_browser_use_tools_marks_save_post_as_done(monkeypatch) -> None:
    captured_actions: dict[str, object] = {}

    class FakeActionResult:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeTools:
        def action(self, description: str):
            def decorator(func):
                captured_actions[func.__name__] = func
                return func

            return decorator

    fake_browser_use = types.ModuleType("browser_use")
    fake_browser_use.Tools = FakeTools
    fake_browser_use.ActionResult = FakeActionResult
    monkeypatch.setitem(sys.modules, "browser_use", fake_browser_use)

    posted_content = MemoryPostedContentSink()
    job = PostJob(
        job_id="job_save_1",
        media_path="/tmp/generated.mp4",
        caption="exact caption",
        content_tier="MOF",
        product_name="Explorehd",
        audio_hook_text="Uncover the ocean's clearest secrets.",
        target_niche="underwater photography",
        funnel_position="MOF",
        source_blueprint_id="tpl_b7bbac3bc08e",
    )

    _, saved_urls = social_media_module._build_browser_use_tools(job, posted_content_sink=posted_content)
    result = captured_actions["save_post"](
        "https://www.instagram.com/reel/DWwHnoiggB9/",
        content_tier="MOF",
    )

    assert saved_urls == ["https://www.instagram.com/reel/DWwHnoiggB9/"]
    assert posted_content.get_posted_content("https://www.instagram.com/reel/DWwHnoiggB9/") is not None
    assert result.kwargs["is_done"] is True
    assert result.kwargs["success"] is True
    assert "POST SAVED" in result.kwargs["extracted_content"]


def test_build_posted_content_record_matches_job_metadata() -> None:
    job = PostJob(
        job_id="job_2",
        media_path="/tmp/generated.mp4",
        caption="exact caption",
        hashtags=["#one", "#two"],
        content_tier="TOF",
        funnel_position="TOF",
        product_name="Widget",
        product_tags=["@widgetbrand"],
        brand_tags=["@widgetbrand", "@creator"],
        audio_hook_text="This changed everything",
        target_niche="gadgets",
        thumbnail_text="TOP PICK",
        source_blueprint_id="bp_456",
    )

    record = social_media_module._build_posted_content_record(
        job,
        post_url="https://www.instagram.com/reel/XYZ999/",
    )

    assert record.post_url.endswith("/XYZ999/")
    assert record.product_tag == "@widgetbrand"
    assert record.analytics_check_intervals == ["day_1", "day_3", "week_1"]
    assert record.brand_tags == ["@widgetbrand", "@creator"]


def test_classify_comment_matches_requested_categories() -> None:
    assert social_media_module.classify_comment("where can i buy this??").value == "purchase_intent"
    assert social_media_module.classify_comment("what product is that?").value == "question"
    assert social_media_module.classify_comment("love this omg").value == "compliment"
    assert social_media_module.classify_comment("this doesnt work for me").value == "criticism"
    assert social_media_module.classify_comment("follow me for free money").value == "spam"
    assert social_media_module.classify_comment("just saw this on my feed").value == "general"


def test_build_comment_engagement_tools_marks_terminal_paths_as_done(monkeypatch) -> None:
    captured_actions: dict[str, object] = {}

    class FakeActionResult:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeTools:
        def action(self, description: str):
            def decorator(func):
                captured_actions[func.__name__] = func
                return func

            return decorator

    fake_browser_use = types.ModuleType("browser_use")
    fake_browser_use.Tools = FakeTools
    fake_browser_use.ActionResult = FakeActionResult
    monkeypatch.setitem(sys.modules, "browser_use", fake_browser_use)

    post = PostedContentRecord(
        post_url="https://www.instagram.com/reel/ENGDONE/",
        job_id="job_engage_done",
    )
    posted_content = MemoryPostedContentSink()
    _, state = social_media_module._build_comment_engagement_tools(
        post,
        posted_content_sink=posted_content,
        existing_signatures=set(),
        run_id="run_done",
    )

    no_action_result = captured_actions["no_action_needed"]("all visible comments were already handled")
    failure_result = captured_actions["report_engagement_failure"]("reply composer blocked", "reply")

    assert state["no_action_called"] is True
    assert state["no_action_reason"] == "all visible comments were already handled"
    assert state["failure_reason"] == "reply - reply composer blocked"
    assert no_action_result.kwargs["is_done"] is True
    assert no_action_result.kwargs["success"] is True
    assert failure_result.kwargs["is_done"] is True
    assert failure_result.kwargs["success"] is False


@pytest.mark.asyncio
async def test_engage_post_comments_builds_prompt_and_updates_summary(monkeypatch) -> None:
    browser = _CapturingBrowser(
        AgentResult(
            task_id="task_engage_1",
            success=True,
            provider=ProviderType.MOCK,
            output={"final_result": "done"},
        )
    )
    posted_content = MemoryPostedContentSink()
    post = PostedContentRecord(
        post_url="https://www.instagram.com/reel/ENG123/",
        job_id="job_engage_1",
        caption="demo caption",
        product_name="Demo Product",
        target_niche="beauty",
    )
    posted_content.persist_posted_content(post)
    pipeline = SocialMediaPipeline(
        browser=browser,
        analytics_sink=MemoryAnalyticsSink(),
        posted_content_sink=posted_content,
        templates=MemoryTemplateStore(),
    )

    def fake_build_comment_engagement_tools(post_record, *, posted_content_sink, existing_signatures, run_id):
        reply = CommentReplyRecord(
            reply_id="reply_1",
            post_url=post_record.post_url,
            post_id="ENG123",
            run_id=run_id,
            commenter_handle="skinfan",
            comment_text="where can i buy this?",
            comment_signature="skinfan::where can i buy this?",
            comment_category=social_media_module.CommentCategory.PURCHASE_INTENT,
            response_text="check the link in bio and lmk if you have questions ✨",
        )
        posted_content_sink.persist_comment_reply(reply)
        return object(), {
            "logged_replies": [reply],
            "no_action_reason": "",
            "no_action_called": False,
            "failure_reason": "",
        }

    monkeypatch.setattr(
        social_media_module,
        "_build_comment_engagement_tools",
        fake_build_comment_engagement_tools,
    )

    summary = await pipeline.engage_post_comments(
        post.post_url,
        persona=CommentEngagementPersona(persona_name="TechTok Sarah", instagram_handle="@techtok.sarah"),
        dry_run=False,
        run_id="run_123",
    )

    assert summary.status == CommentEngagementStatus.REPLIED
    assert summary.total_replies_logged == 1
    assert summary.replies_posted_this_run == 1
    assert posted_content.get_posted_content(post.post_url).engagement_summary is not None
    task = browser.tasks[0]
    assert task.metadata["pipeline"] == "social_comment_engagement"
    assert task.url == post.post_url
    assert "@techtok.sarah" in task.description
    assert "Stop after replying to 5 comments total." in task.description
    assert task.metadata["browser_use_browser"] is None


@pytest.mark.asyncio
async def test_engage_post_comments_requests_dedicated_local_browser_window(monkeypatch) -> None:
    browser = _CapturingBrowser(
        AgentResult(
            task_id="task_engage_window",
            success=True,
            provider=ProviderType.MOCK,
            output={"final_result": "done"},
        )
    )
    posted_content = MemoryPostedContentSink()
    post = PostedContentRecord(
        post_url="https://www.instagram.com/reel/ENG999/",
        job_id="job_engage_window",
        caption="demo caption",
        product_name="Demo Product",
    )
    posted_content.persist_posted_content(post)
    pipeline = SocialMediaPipeline(
        browser=browser,
        analytics_sink=MemoryAnalyticsSink(),
        posted_content_sink=posted_content,
        templates=MemoryTemplateStore(),
        browser_runtime_env={
            "BROWSER_USE_CDP_URL": "http://localhost:9222",
            "CHROME_EXECUTABLE_PATH": "/usr/bin/google-chrome",
            "CHROME_USER_DATA_DIR": "/tmp/browser-profile-clone",
            "CHROME_PROFILE_DIRECTORY": "Profile 9",
        },
    )

    def fake_build_comment_engagement_tools(post_record, *, posted_content_sink, existing_signatures, run_id):
        return object(), {
            "logged_replies": [],
            "no_action_reason": "nothing to do",
            "no_action_called": True,
            "failure_reason": "",
        }

    monkeypatch.setattr(
        social_media_module,
        "_build_comment_engagement_tools",
        fake_build_comment_engagement_tools,
    )

    await pipeline.engage_post_comments(post.post_url, persona=None, dry_run=False)

    task = browser.tasks[0]
    assert task.metadata["browser_use_browser"] == {
        "cdp_url": None,
        "headless": False,
        "keep_alive": False,
        "isolate_local_browser_profile": True,
        "executable_path": "/usr/bin/google-chrome",
        "user_data_dir": "/tmp/browser-profile-clone",
        "profile_directory": "Profile 9",
        "extra_kwargs": {"enable_default_extensions": False},
    }


@pytest.mark.asyncio
async def test_engage_post_comments_uses_existing_reply_signatures(monkeypatch) -> None:
    browser = _CapturingBrowser(
        AgentResult(
            task_id="task_engage_2",
            success=True,
            provider=ProviderType.MOCK,
            output={"final_result": "done"},
        )
    )
    posted_content = MemoryPostedContentSink()
    post = PostedContentRecord(
        post_url="https://www.instagram.com/reel/ENG456/",
        job_id="job_engage_2",
        caption="demo caption",
        product_name="Demo Product",
    )
    posted_content.persist_posted_content(post)
    posted_content.persist_comment_reply(
        CommentReplyRecord(
            reply_id="reply_existing",
            post_url=post.post_url,
            commenter_handle="loyalfan",
            comment_text="love this",
            comment_signature="loyalfan::love this",
            response_text="thank you so much 🫶",
        )
    )
    pipeline = SocialMediaPipeline(
        browser=browser,
        analytics_sink=MemoryAnalyticsSink(),
        posted_content_sink=posted_content,
        templates=MemoryTemplateStore(),
    )
    captured_signatures: set[str] = set()

    def fake_build_comment_engagement_tools(post_record, *, posted_content_sink, existing_signatures, run_id):
        captured_signatures.update(existing_signatures)
        return object(), {
            "logged_replies": [],
            "no_action_reason": "all visible comments were already handled",
            "no_action_called": True,
            "failure_reason": "",
        }

    monkeypatch.setattr(
        social_media_module,
        "_build_comment_engagement_tools",
        fake_build_comment_engagement_tools,
    )

    summary = await pipeline.engage_post_comments(post.post_url, persona=None, dry_run=False)

    assert captured_signatures == {"loyalfan::love this"}
    assert summary.status == CommentEngagementStatus.NO_ACTION_NEEDED
    assert "loyalfan::love this" in browser.tasks[0].description


@pytest.mark.asyncio
async def test_engage_post_comments_dry_run_skips_browser_execution() -> None:
    browser = _CapturingBrowser(
        AgentResult(
            task_id="task_engage_3",
            success=True,
            provider=ProviderType.MOCK,
            output={},
        )
    )
    posted_content = MemoryPostedContentSink()
    post = PostedContentRecord(
        post_url="https://www.instagram.com/reel/ENG789/",
        job_id="job_engage_3",
        caption="demo caption",
        product_name="Demo Product",
    )
    posted_content.persist_posted_content(post)
    pipeline = SocialMediaPipeline(
        browser=browser,
        analytics_sink=MemoryAnalyticsSink(),
        posted_content_sink=posted_content,
        templates=MemoryTemplateStore(),
    )

    summary = await pipeline.engage_post_comments(post.post_url, persona=None, dry_run=True)

    assert summary.status == CommentEngagementStatus.SKIPPED
    assert summary.last_reason == "dry_run_preview"
    assert browser.tasks == []
