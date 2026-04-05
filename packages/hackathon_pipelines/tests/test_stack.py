from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from packages.shared.config import get_settings
from PIL import Image

import hackathon_pipelines as hackathon_module
from hackathon_pipelines import build_dry_run_stack, build_runtime_stack
from hackathon_pipelines.adapters import live_api as live_api_module
from hackathon_pipelines.adapters.live_api import VeoVideoGenerator
from hackathon_pipelines.contracts import (
    CommentEngagementStatus,
    CommentEngagementSummary,
    GenerationBundle,
    PostAnalyticsSnapshot,
    TemplatePerformanceLabel,
    VeoGenerationConfig,
)
from hackathon_pipelines.stores import SQLiteHackathonStore


def test_extract_json_object_handles_wrapped_json() -> None:
    parsed = live_api_module._extract_json_object(
        'Here you go:\n```json\n{"user_prompt":"show the product","notes":"ok"}\n```'
    )
    assert parsed["user_prompt"] == "show the product"


def test_response_text_falls_back_to_candidate_parts() -> None:
    response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[SimpleNamespace(text='{"decision":"iterate","reason":"ok","veo_prompt_draft":"demo"}')]
                )
            )
        ],
    )
    assert '"decision":"iterate"' in live_api_module._response_text(response)


def test_veo_generator_defaults_to_fast_model() -> None:
    veo = VeoVideoGenerator(dry_run=True)
    assert veo._model == "veo-3.1-fast-generate-preview"


def test_veo_generator_defaults_to_vertex_fast_model(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    veo = VeoVideoGenerator(dry_run=True)
    assert veo._model == "veo-3.1-fast-generate-001"


@pytest.mark.asyncio
async def test_reel_discovery_creates_template() -> None:
    stack = build_dry_run_stack()
    summary = await stack.orchestrator.run_reel_to_template_cycle()
    assert summary.templates_created >= 1
    assert stack.templates.list_templates()


@pytest.mark.asyncio
async def test_product_to_video_dry_run(tmp_path) -> None:
    stack = build_dry_run_stack()
    p = tmp_path / "product.png"
    p.write_bytes(b"fake")
    a = tmp_path / "avatar.png"
    a.write_bytes(b"fake")
    summary = await stack.orchestrator.run_product_to_video(
        product_image_path=str(p),
        avatar_image_path=str(a),
    )
    assert summary.generations == 1


@pytest.mark.asyncio
async def test_veo_dry_run_generates_local_mp4(tmp_path) -> None:
    product = tmp_path / "product.png"
    Image.new("RGB", (64, 64), color=(220, 120, 80)).save(product)
    avatar = tmp_path / "avatar.png"
    Image.new("RGB", (64, 64), color=(80, 120, 220)).save(avatar)
    bundle = GenerationBundle(
        bundle_id="bundle_1",
        template_id="tpl_1",
        product_id="prod_1",
        veo_prompt="Create a quick UGC reel.",
        product_title="Demo Camera",
        product_description="Compact camera for creators.",
        creative_brief="Show the avatar presenting the product.",
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        reference_image_paths=[str(product), str(avatar)],
    )
    veo = VeoVideoGenerator(dry_run=True, output_dir=tmp_path / "videos")

    artifact = await veo.generate_ugc_video(bundle)

    assert artifact.video_path is not None
    assert artifact.video_path.endswith(".mp4")
    assert (tmp_path / "videos").exists()


@pytest.mark.asyncio
async def test_veo_live_generator_uses_bundle_generation_config(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    class FakeImage:
        @staticmethod
        def from_file(*, location: str):
            return {"location": location}

    class FakeVideo:
        uri = "https://example.com/generated.mp4"

        def save(self, path: str) -> None:
            captured["saved_path"] = path
            Path(path).write_bytes(b"mp4")

    class FakeModels:
        async def generate_videos(self, *, model, prompt, config):
            captured["model"] = model
            captured["prompt"] = prompt
            captured["config"] = config
            return SimpleNamespace(
                done=True,
                result=SimpleNamespace(generated_videos=[SimpleNamespace(video=FakeVideo())]),
            )

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)
            self.aio = SimpleNamespace(
                models=FakeModels(),
                operations=SimpleNamespace(get=lambda operation: operation),
            )
            self.files = SimpleNamespace(download=lambda *, file: captured.setdefault("downloaded_uri", file.uri))

    monkeypatch.setattr(live_api_module.genai, "Client", FakeClient)
    monkeypatch.setattr(live_api_module.genai_types, "GenerateVideosConfig", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(
        live_api_module.genai_types,
        "VideoGenerationReferenceImage",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(live_api_module.genai_types, "Image", FakeImage)
    monkeypatch.setattr(live_api_module.asyncio, "to_thread", fake_to_thread)

    product = tmp_path / "product.png"
    avatar = tmp_path / "avatar.png"
    Image.new("RGB", (64, 64), color=(220, 120, 80)).save(product)
    Image.new("RGB", (64, 64), color=(80, 120, 220)).save(avatar)
    bundle = GenerationBundle(
        bundle_id="bundle_live",
        template_id="tpl_1",
        product_id="prod_1",
        veo_prompt="Combined locked Veo prompt.",
        product_title="Demo Camera",
        product_description="Compact camera for creators.",
        creative_brief="Show the avatar presenting the product.",
        generation_config=VeoGenerationConfig(aspect_ratio="1:1", duration_seconds=5),
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        reference_image_paths=[str(product), str(avatar)],
    )
    veo = VeoVideoGenerator(dry_run=False, api_key="test-api-key", output_dir=tmp_path / "videos")

    artifact = await veo.generate_ugc_video(bundle)

    assert captured["api_key"] == "test-api-key"
    assert captured["config"].aspect_ratio == "1:1"
    assert captured["config"].duration_seconds == 5
    assert artifact.video_path is not None
    assert Path(artifact.video_path).exists()


@pytest.mark.asyncio
async def test_veo_live_generator_uses_vertex_client_without_api_key(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    class FakeImage:
        @staticmethod
        def from_file(*, location: str):
            return {"location": location}

    class FakeVideo:
        uri = "https://example.com/generated.mp4"

        def save(self, path: str) -> None:
            Path(path).write_bytes(b"mp4")

    class FakeModels:
        async def generate_videos(self, *, model, prompt, config):
            captured["model"] = model
            return SimpleNamespace(
                done=True,
                result=SimpleNamespace(generated_videos=[SimpleNamespace(video=FakeVideo())]),
            )

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)
            self.aio = SimpleNamespace(
                models=FakeModels(),
                operations=SimpleNamespace(get=lambda operation: operation),
            )
            self.files = SimpleNamespace(download=lambda *, file: None)

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setattr(live_api_module.genai, "Client", FakeClient)
    monkeypatch.setattr(live_api_module.genai_types, "GenerateVideosConfig", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(
        live_api_module.genai_types,
        "VideoGenerationReferenceImage",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(live_api_module.genai_types, "Image", FakeImage)
    monkeypatch.setattr(live_api_module.asyncio, "to_thread", fake_to_thread)

    product = tmp_path / "product.png"
    avatar = tmp_path / "avatar.png"
    Image.new("RGB", (64, 64), color=(220, 120, 80)).save(product)
    Image.new("RGB", (64, 64), color=(80, 120, 220)).save(avatar)
    bundle = GenerationBundle(
        bundle_id="bundle_vertex",
        template_id="tpl_1",
        product_id="prod_1",
        veo_prompt="Combined locked Veo prompt.",
        product_title="Demo Camera",
        product_description="Compact camera for creators.",
        creative_brief="Show the avatar presenting the product.",
        generation_config=VeoGenerationConfig(aspect_ratio="9:16", duration_seconds=8),
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        reference_image_paths=[str(product), str(avatar)],
    )
    veo = VeoVideoGenerator(dry_run=False, api_key="should-not-be-used", output_dir=tmp_path / "videos")

    artifact = await veo.generate_ugc_video(bundle)

    assert "api_key" not in captured
    assert captured["model"] == "veo-3.1-fast-generate-001"
    assert artifact.video_path is not None


@pytest.mark.asyncio
async def test_decide_template_disposition_falls_back_when_gemini_json_is_invalid(monkeypatch) -> None:
    class FakeModels:
        async def generate_content(self, *, model, contents, config):
            return SimpleNamespace(text="not json at all", candidates=[])

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr(live_api_module.genai, "Client", FakeClient)

    agent = live_api_module.GeminiTemplateAgent(dry_run=False, api_key="test-key")
    decision, reason, draft = await agent.decide_template_disposition(
        live_api_module.VideoStructureRecord(
            record_id="struct_1",
            source_reel_id="reel_1",
            major_scenes=["wide shot", "close-up"],
            hook_pattern="fast opener",
            audio_music_cues="upbeat",
            visual_style="creator",
            sequence_description="open then demo",
            on_screen_text_notes="",
            raw_analysis_text="{}",
        ),
        peer_templates=[],
    )

    assert decision.value == "iterate"
    assert reason == "invalid_json_fallback"
    assert "fast opener" in draft


@pytest.mark.asyncio
async def test_generation_bundle_includes_product_description_and_feedback_context(tmp_path) -> None:
    stack = build_dry_run_stack()
    await stack.orchestrator.run_reel_to_template_cycle()
    template = stack.templates.list_templates()[0]
    template.performance_label = TemplatePerformanceLabel.SUCCESSFUL_REUSE
    stack.templates.update_template(template)

    product = stack.products.top_by_score(limit=1)
    if not product:
        p = tmp_path / "product.png"
        p.write_bytes(b"fake")
        a = tmp_path / "avatar.png"
        a.write_bytes(b"fake")
        await stack.orchestrator.run_product_to_video(
            product_image_path=str(p),
            avatar_image_path=str(a),
        )
        product = stack.products.top_by_score(limit=1)

    p = tmp_path / "product2.png"
    p.write_bytes(b"fake")
    a = tmp_path / "avatar2.png"
    a.write_bytes(b"fake")
    bundle, _artifact = await stack.orchestrator._video.generate_for_product(  # type: ignore[attr-defined]
        template,
        product[0],
        product_image_path=str(p),
        avatar_image_path=str(a),
    )
    assert bundle.product_title == product[0].title
    assert bundle.product_description
    assert bundle.creative_brief
    assert "successful_reuse" in str(bundle.prior_template_metadata.get("performance_label"))


@pytest.mark.asyncio
async def test_publish_and_feedback_updates_template(tmp_path) -> None:
    stack = build_dry_run_stack()
    await stack.orchestrator.run_reel_to_template_cycle()
    tpl = stack.templates.list_templates()[0]
    v = tmp_path / "out.mp4"
    v.write_bytes(b"")
    summary = await stack.orchestrator.run_publish_and_feedback(
        media_path=str(v),
        caption="Test #hackathon",
        template_id=tpl.template_id,
        dry_run=True,
    )
    assert summary.posts == 1
    assert stack.analytics.snapshots
    updated = stack.templates.get_template(tpl.template_id)
    assert updated is not None
    assert updated.performance_label is not None


@pytest.mark.asyncio
async def test_publish_and_feedback_waits_for_media_and_runs_followups_concurrently(tmp_path, monkeypatch) -> None:
    from browser_runtime.types import AgentResult, ProviderType

    stack = build_dry_run_stack()
    await stack.orchestrator.run_reel_to_template_cycle()
    tpl = stack.templates.list_templates()[0]
    video_path = tmp_path / "late.mp4"

    async def create_video_file() -> None:
        await asyncio.sleep(0.05)
        video_path.write_bytes(b"mp4")

    publish_seen: dict[str, bool] = {"called": False}
    running = {"engagement": False, "analytics": False}
    overlap = {"seen": False}

    async def fake_publish_reel(job):
        assert video_path.exists()
        publish_seen["called"] = True
        return AgentResult(
            task_id="publish_concurrent",
            success=True,
            provider=ProviderType.MOCK,
            output={"post_url": "https://www.instagram.com/reel/PAR123/", "post_id": "PAR123"},
        )

    async def fake_engage_post_comments(post_url: str, *, persona, dry_run: bool, run_id: str | None = None):
        assert post_url.endswith("/PAR123/")
        running["engagement"] = True
        overlap["seen"] = overlap["seen"] or running["analytics"]
        await asyncio.sleep(0.05)
        overlap["seen"] = overlap["seen"] or running["analytics"]
        running["engagement"] = False
        return CommentEngagementSummary(
            status=CommentEngagementStatus.REPLIED,
            total_replies_logged=1,
            replies_posted_this_run=1,
        )

    async def fake_fetch_post_analytics(post_id: str, *, dry_run: bool = True):
        assert post_id == "PAR123"
        running["analytics"] = True
        overlap["seen"] = overlap["seen"] or running["engagement"]
        await asyncio.sleep(0.05)
        overlap["seen"] = overlap["seen"] or running["engagement"]
        running["analytics"] = False
        return PostAnalyticsSnapshot(snapshot_id="snap_parallel", post_id=post_id, views=100_000, likes=5_000)

    social = stack.orchestrator._social  # type: ignore[attr-defined]
    monkeypatch.setattr(social, "publish_reel", fake_publish_reel)
    monkeypatch.setattr(social, "engage_post_comments", fake_engage_post_comments)
    monkeypatch.setattr(social, "fetch_post_analytics", fake_fetch_post_analytics)

    creator_task = asyncio.create_task(create_video_file())
    summary = await stack.orchestrator.run_publish_and_feedback(
        media_path=str(video_path),
        caption="parallel test",
        template_id=tpl.template_id,
        dry_run=False,
    )
    await creator_task

    assert publish_seen["called"] is True
    assert overlap["seen"] is True
    assert summary.posts == 1
    assert "engagement_status=replied" in summary.notes


@pytest.mark.asyncio
async def test_closed_loop_cycle_dry_run(tmp_path) -> None:
    stack = build_dry_run_stack()
    p = tmp_path / "product.png"
    p.write_bytes(b"fake")
    a = tmp_path / "avatar.png"
    a.write_bytes(b"fake")
    m = tmp_path / "generated.mp4"
    summary = await stack.orchestrator.run_closed_loop_cycle(
        product_image_path=str(p),
        avatar_image_path=str(a),
        media_path=str(m),
        dry_run=True,
    )
    assert summary.reel_summary.templates_created >= 1
    assert summary.product_summary.generations == 1
    assert summary.publish_summary is not None
    assert summary.publish_summary.posts == 1
    assert summary.template_id is not None


@pytest.mark.asyncio
async def test_runtime_stack_persists_to_sqlite(tmp_path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    p = tmp_path / "product.png"
    p.write_bytes(b"fake")
    a = tmp_path / "avatar.png"
    a.write_bytes(b"fake")
    m = tmp_path / "generated.mp4"
    await stack.orchestrator.run_closed_loop_cycle(
        product_image_path=str(p),
        avatar_image_path=str(a),
        media_path=str(m),
        dry_run=True,
    )

    reopened = SQLiteHackathonStore(db_path)
    assert reopened.list_templates()
    assert reopened.top_candidates(limit=1)
    assert reopened.list_snapshots()


def test_build_runtime_stack_constructs_live_browser_use_provider_from_env(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, llm_model: str, dry_run: bool, *, browser_config) -> None:
            captured["llm_model"] = llm_model
            captured["dry_run"] = dry_run
            captured["browser_kwargs"] = browser_config.to_browser_kwargs()

    monkeypatch.setattr(hackathon_module, "BrowserUseProvider", FakeProvider)
    monkeypatch.setenv("BROWSER_USE_CDP_URL", "http://127.0.0.1:9666")
    monkeypatch.setenv("DRY_RUN", "false")
    get_settings.cache_clear()

    stack = build_runtime_stack(dry_run=False, db_path=tmp_path / "live.sqlite3")

    assert captured["llm_model"] == "ChatBrowserUse"
    assert captured["dry_run"] is False
    assert captured["browser_kwargs"] == {
        "cdp_url": "http://127.0.0.1:9666",
        "headless": False,
        "keep_alive": True,
    }
    assert stack.store.db_path == tmp_path / "live.sqlite3"
    get_settings.cache_clear()


def test_build_runtime_stack_disables_default_extensions_for_local_live_browser(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, llm_model: str, dry_run: bool, *, browser_config) -> None:
            captured["llm_model"] = llm_model
            captured["dry_run"] = dry_run
            captured["browser_kwargs"] = browser_config.to_browser_kwargs()

    monkeypatch.setattr(hackathon_module, "BrowserUseProvider", FakeProvider)
    monkeypatch.delenv("BROWSER_USE_CDP_URL", raising=False)
    monkeypatch.setenv("CHROME_EXECUTABLE_PATH", "/usr/bin/google-chrome")
    monkeypatch.setenv("CHROME_USER_DATA_DIR", "/home/kevin/.config/google-chrome")
    monkeypatch.setenv("CHROME_PROFILE_DIRECTORY", "Profile 9")
    monkeypatch.setenv("DRY_RUN", "false")
    get_settings.cache_clear()

    build_runtime_stack(dry_run=False, db_path=tmp_path / "live.sqlite3")

    assert captured["llm_model"] == "ChatBrowserUse"
    assert captured["dry_run"] is False
    assert captured["browser_kwargs"] == {
        "executable_path": "/usr/bin/google-chrome",
        "user_data_dir": "/home/kevin/.config/google-chrome",
        "profile_directory": "Profile 9",
        "headless": False,
        "keep_alive": True,
        "enable_default_extensions": False,
    }
    get_settings.cache_clear()


def test_build_runtime_stack_auto_detects_local_live_browser_defaults(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, llm_model: str, dry_run: bool, *, browser_config) -> None:
            captured["llm_model"] = llm_model
            captured["dry_run"] = dry_run
            captured["browser_kwargs"] = browser_config.to_browser_kwargs()

    monkeypatch.setattr(hackathon_module, "BrowserUseProvider", FakeProvider)
    monkeypatch.delenv("BROWSER_USE_CDP_URL", raising=False)
    monkeypatch.delenv("CHROME_EXECUTABLE_PATH", raising=False)
    monkeypatch.delenv("CHROME_USER_DATA_DIR", raising=False)
    monkeypatch.delenv("CHROME_PROFILE_DIRECTORY", raising=False)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr(
        hackathon_module,
        "build_effective_browser_runtime_env",
        lambda **kwargs: {
            "CHROME_EXECUTABLE_PATH": "/auto/google-chrome",
            "CHROME_USER_DATA_DIR": "/auto/user-data",
            "CHROME_PROFILE_DIRECTORY": "Profile 4",
            "BROWSER_USE_HEADLESS": "false",
        },
    )
    get_settings.cache_clear()

    build_runtime_stack(dry_run=False, db_path=tmp_path / "auto.sqlite3")

    assert captured["llm_model"] == "ChatBrowserUse"
    assert captured["dry_run"] is False
    assert captured["browser_kwargs"] == {
        "executable_path": "/auto/google-chrome",
        "user_data_dir": "/auto/user-data",
        "profile_directory": "Profile 4",
        "headless": False,
        "keep_alive": True,
        "enable_default_extensions": False,
    }
    get_settings.cache_clear()


def test_build_runtime_stack_prefers_request_browser_runtime_env_override(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, llm_model: str, dry_run: bool, *, browser_config) -> None:
            captured["browser_kwargs"] = browser_config.to_browser_kwargs()

    monkeypatch.setattr(hackathon_module, "BrowserUseProvider", FakeProvider)
    monkeypatch.setenv("BROWSER_USE_CDP_URL", "http://127.0.0.1:9553")
    monkeypatch.setenv("DRY_RUN", "false")
    get_settings.cache_clear()

    build_runtime_stack(
        dry_run=False,
        db_path=tmp_path / "override.sqlite3",
        browser_runtime_env={
            "BROWSER_USE_CDP_URL": "http://127.0.0.1:9222",
            "BROWSER_USE_HEADLESS": "false",
        },
    )

    assert captured["browser_kwargs"] == {
        "cdp_url": "http://127.0.0.1:9222",
        "headless": False,
        "keep_alive": True,
    }
    get_settings.cache_clear()


def test_build_runtime_stack_ignores_chrome_fields_when_cdp_is_present(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, llm_model: str, dry_run: bool, *, browser_config) -> None:
            captured["browser_kwargs"] = browser_config.to_browser_kwargs()

    monkeypatch.setattr(hackathon_module, "BrowserUseProvider", FakeProvider)
    monkeypatch.setenv("BROWSER_USE_CDP_URL", "http://127.0.0.1:9222")
    monkeypatch.setenv("CHROME_EXECUTABLE_PATH", "/usr/bin/google-chrome")
    monkeypatch.setenv("CHROME_USER_DATA_DIR", "/home/kevin/.config/google-chrome")
    monkeypatch.setenv("CHROME_PROFILE_DIRECTORY", "Profile 3")
    monkeypatch.setenv("DRY_RUN", "false")
    get_settings.cache_clear()

    build_runtime_stack(dry_run=False, db_path=tmp_path / "mixed.sqlite3")

    assert captured["browser_kwargs"] == {
        "cdp_url": "http://127.0.0.1:9222",
        "headless": False,
        "keep_alive": True,
    }
    get_settings.cache_clear()
