"""Tests for the FastAPI control plane."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from packages.shared.config import get_settings
from packages.shared.db import init_db
from services.control_plane.app import app


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
    r = await client.post("/pipeline/demo")
    assert r.status_code == 200
    data = r.json()
    assert data.get("demo_complete") is True
    assert data["pipeline"] == "hackathon_closed_loop"
    assert data["summary"]["reel_summary"]["templates_created"] >= 1
    assert data["summary"]["product_summary"]["generations"] == 1
    assert data["summary"]["publish_summary"]["posts"] == 1


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

    start = await client.post("/pipeline/loop/start", json={"interval_seconds": 0.01, "max_cycles": 1})
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

    r = await client.post("/pipeline/gemini-orchestrate", json={"instruction": "Run the full pipeline", "max_turns": 5})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["pipeline"] == "gemini_meta_orchestrator"
    assert data["final_text"] == "Gemini orchestrator completed the pipeline."
    assert data["turns_used"] == 3
