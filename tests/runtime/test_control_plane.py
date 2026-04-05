"""Tests for the FastAPI control plane."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from packages.shared.config import get_settings
from packages.shared.db import init_db
from services.control_plane.app import (
    BrowserRuntimeRequest,
    GeminiOrchestrationRequest,
    HackathonDemoRequest,
    _browser_runtime_env_from_request,
    _hackathon_defaults,
    app,
)


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("HACKATHON_PIPELINE_DB_PATH", str(tmp_path / "hackathon.sqlite3"))
    monkeypatch.setenv("HACKATHON_PRODUCT_IMAGE_PATH", str(tmp_path / "assets" / "product.png"))
    monkeypatch.setenv("HACKATHON_AVATAR_IMAGE_PATH", str(tmp_path / "assets" / "avatar.png"))
    monkeypatch.setenv("HACKATHON_MEDIA_PATH", str(tmp_path / "media" / "generated.mp4"))
    monkeypatch.setenv("HACKATHON_LOOP_WORKDIR", str(tmp_path / "loop"))
    monkeypatch.setenv("HACKATHON_LOOP_INTERVAL_SECONDS", "0.05")
    get_settings.cache_clear()
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    runner = getattr(app.state, "hackathon_loop_runner", None)
    if runner is not None and runner.is_running:
        await runner.stop()
    app.state.hackathon_loop_runner = None
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "abunnytech"


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "dry_run" in data
    assert "stage5_monetize" in data
    assert "hackathon_loop_running" in data


@pytest.mark.asyncio
async def test_create_default_identity(client: AsyncClient):
    r = await client.post("/identity/default")
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Avery Bytes"


@pytest.mark.asyncio
async def test_list_identities(client: AsyncClient):
    await client.post("/identity/default")
    r = await client.get("/identity")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_demo_pipeline(client: AsyncClient):
    r = await client.post(
        "/pipeline/demo",
        json={
            "browser_runtime": {
                "cdp_url": "http://127.0.0.1:9222",
                "chrome_profile_directory": "Profile 9",
                "headless": False,
            }
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("demo_complete") is True
    assert data["pipeline"] == "hackathon_generate_ready"
    assert data["run"]["status"] == "ready"
    assert data["run"]["selected_template_id"] is not None
    assert data["run"]["caption"]
    assert data["run"]["video_path"]


@pytest.mark.asyncio
async def test_stage_demo_pipeline(client: AsyncClient):
    r = await client.post("/pipeline/stage-demo")
    assert r.status_code == 200
    data = r.json()
    assert data.get("demo_complete") is True
    assert "stage0_identity" in data["stages"]
    assert "stage4_analyze" in data["stages"]


@pytest.mark.asyncio
async def test_hackathon_loop_endpoints(client: AsyncClient):
    initial = await client.get("/pipeline/loop/status")
    assert initial.status_code == 200
    assert initial.json()["running"] is False

    start = await client.post(
        "/pipeline/loop/start", json={"interval_seconds": 0.01, "max_cycles": 1}
    )
    assert start.status_code == 200

    await asyncio.sleep(0.2)
    status = await client.get("/pipeline/loop/status")
    assert status.status_code == 200
    assert status.json()["cycle_count"] >= 1

    stop = await client.post("/pipeline/loop/stop")
    assert stop.status_code == 200
    assert stop.json()["stopped"] is True


@pytest.mark.asyncio
async def test_gemini_orchestration_endpoint(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    @dataclass
    class FakeResult:
        final_text: str | None = "Gemini orchestrator completed the pipeline."
        tool_trace: list[dict] = None  # type: ignore[assignment]
        turns_used: int = 3

        def __post_init__(self):
            if self.tool_trace is None:
                self.tool_trace = [{"name": "run_reel_to_template_cycle"}]

    async def fake_run(orchestrator, *, instruction: str, api_key=None, model=None, max_turns=12):
        assert "Run the full pipeline" in instruction
        assert "product_image_path" in instruction
        assert max_turns == 5
        return FakeResult()

    import hackathon_pipelines

    monkeypatch.setattr(hackathon_pipelines, "run_gemini_pipeline_orchestration", fake_run)

    r = await client.post(
        "/pipeline/gemini-orchestrate",
        json={"instruction": "Run the full pipeline", "max_turns": 5},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["pipeline"] == "gemini_meta_orchestrator"
    assert data["final_text"] == "Gemini orchestrator completed the pipeline."
    assert data["turns_used"] == 3


def test_gemini_orchestration_request_default_instruction_mentions_comments_and_feedback() -> None:
    instruction = GeminiOrchestrationRequest().instruction
    assert "engage comments when live" in instruction
    assert "feed analytics back into the template store" in instruction


@pytest.mark.asyncio
async def test_latest_run_and_post_latest_endpoints(client: AsyncClient):
    before = await client.get("/pipeline/latest-run")
    assert before.status_code == 200
    assert before.json()["run"] is None

    created = await client.post("/pipeline/demo")
    assert created.status_code == 200
    run = created.json()["run"]

    latest = await client.get("/pipeline/latest-run")
    assert latest.status_code == 200
    assert latest.json()["run"]["run_id"] == run["run_id"]

    posted = await client.post("/pipeline/post-latest", json={"dry_run": True})
    assert posted.status_code == 200
    assert posted.json()["run"]["status"] == "posted"
    assert posted.json()["run"]["post_url"]

    engaged = await client.post("/pipeline/engage-latest", json={"dry_run": True})
    assert engaged.status_code == 200
    assert engaged.json()["engagement_summary"]["status"] == "skipped"

    posts = await client.get("/pipeline/posts")
    assert posts.status_code == 200
    assert posts.json()["posts"]
    assert posts.json()["posts"][0]["engagement_summary"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_list_pipeline_runs_returns_recent_history(client: AsyncClient):
    first = await client.post("/pipeline/demo")
    second = await client.post("/pipeline/demo")
    assert first.status_code == 200
    assert second.status_code == 200

    response = await client.get("/pipeline/runs?limit=1")
    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["count"] == 1
    assert len(data["runs"]) == 1
    assert data["runs"][0]["run_id"] == second.json()["run"]["run_id"]


@pytest.mark.asyncio
async def test_generate_video_endpoint_creates_ready_run_from_db_structures(client: AsyncClient):
    created = await client.post("/pipeline/demo")
    assert created.status_code == 200

    generated = await client.post(
        "/pipeline/generate-video",
        json={
            "dry_run": True,
            "product_title": "DB Product",
            "product_description": "Generate from saved structures",
        },
    )
    assert generated.status_code == 200
    data = generated.json()
    assert data["ok"] is True
    assert data["run"]["status"] == "ready"
    assert data["run"]["video_path"]
    assert data["run"]["selected_template_id"] is not None
    assert "source=video_structure_db" in data["run"]["notes"]


@pytest.mark.asyncio
async def test_instant_demo_mode_endpoint_starts_three_parallel_lanes(
    client: AsyncClient,
):
    launched = await client.post("/pipeline/demo-mode", json={"dry_run": True})
    assert launched.status_code == 200
    data = launched.json()

    assert data["ok"] is True
    assert data["pipeline"] == "instant_demo_mode"
    assert data["background_generation_started"] is True
    assert data["parallel_lanes"] == [
        "reel_discovery_to_video_structure",
        "video_structure_to_video_gen_and_instagram_posting",
        "comment_engagement",
    ]


@pytest.mark.asyncio
async def test_post_latest_rejects_when_no_run_exists(client: AsyncClient):
    response = await client.post("/pipeline/post-latest", json={"dry_run": True})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_database_explorer_endpoints(client: AsyncClient):
    demo = await client.post("/pipeline/demo")
    assert demo.status_code == 200

    listing = await client.get("/pipeline/databases")
    assert listing.status_code == 200
    databases = listing.json()["databases"]
    assert databases
    selected = next(item for item in databases if item["exists"])

    detail = await client.get(f"/pipeline/databases/{selected['db_key']}")
    assert detail.status_code == 200
    database = detail.json()["database"]
    assert database["db_key"] == selected["db_key"]
    assert "table_summaries" in database


def test_browser_runtime_env_from_request() -> None:
    env = _browser_runtime_env_from_request(
        BrowserRuntimeRequest(
            cdp_url="http://127.0.0.1:9222",
            chrome_executable_path="/usr/bin/google-chrome",
            chrome_user_data_dir="/home/kevin/.config/google-chrome",
            chrome_profile_directory="Profile 9",
            headless=False,
        )
    )

    assert env == {
        "BROWSER_USE_CDP_URL": "http://127.0.0.1:9222",
        "CHROME_EXECUTABLE_PATH": "/usr/bin/google-chrome",
        "CHROME_USER_DATA_DIR": "/home/kevin/.config/google-chrome",
        "CHROME_PROFILE_DIRECTORY": "Profile 9",
        "BROWSER_USE_HEADLESS": "false",
    }


def test_hackathon_defaults_allows_missing_media_output_for_generation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = tmp_path / "assets" / "product.png"
    avatar = tmp_path / "assets" / "avatar.png"
    product.parent.mkdir(parents=True, exist_ok=True)
    avatar.parent.mkdir(parents=True, exist_ok=True)
    product.write_bytes(b"product")
    avatar.write_bytes(b"avatar")

    media_path = tmp_path / "output" / "hackathon_videos" / "generated_reel.mp4"
    monkeypatch.setenv("HACKATHON_PRODUCT_IMAGE_PATH", str(product))
    monkeypatch.setenv("HACKATHON_AVATAR_IMAGE_PATH", str(avatar))
    monkeypatch.setenv("HACKATHON_MEDIA_PATH", str(media_path))
    get_settings.cache_clear()

    assets = _hackathon_defaults(HackathonDemoRequest(), dry_run=False)

    assert assets["product_image_path"] == str(product)
    assert assets["avatar_image_path"] == str(avatar)
    assert assets["media_path"] == str(media_path)
    assert media_path.parent.exists()
    assert not media_path.exists()
