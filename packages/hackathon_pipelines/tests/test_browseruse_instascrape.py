from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from browser_runtime.providers.mock import MockProvider
from browser_runtime.types import AgentResult, ProviderType
from httpx import Request, Response

from hackathon_pipelines.adapters.facade import BrowserProviderFacade
from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, TwelveLabsUnderstanding
from hackathon_pipelines.browseruse_instascrape import (
    load_instascrape_snapshot,
    load_reel_surface_metrics_from_instascrape,
    make_instascrape_metrics_loader,
)
from hackathon_pipelines.pipelines import reel_discovery as reel_discovery_module
from hackathon_pipelines.pipelines.reel_discovery import ReelDiscoveryPipeline, ReelDiscoverySearchConfig
from hackathon_pipelines.stores.memory import MemoryReelSink, MemoryTemplateStore


def _seed_instascrape_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE creators (
                handle TEXT PRIMARY KEY,
                platform TEXT,
                followers INTEGER,
                bio TEXT,
                source TEXT,
                source_hashtag TEXT,
                priority_score REAL,
                total_reels_saved INTEGER,
                total_outliers INTEGER,
                avg_value_score REAL,
                best_reel_views INTEGER,
                is_active INTEGER,
                skip_reason TEXT
            );

            CREATE TABLE discovered_content (
                creator_handle TEXT NOT NULL,
                reel_url TEXT PRIMARY KEY,
                view_count INTEGER NOT NULL,
                like_count INTEGER NOT NULL,
                comment_count INTEGER DEFAULT 0,
                creator_followers INTEGER DEFAULT 0,
                audio_name TEXT,
                posted_date TEXT,
                content_tier TEXT,
                hook_pattern TEXT,
                likely_bof INTEGER DEFAULT 0,
                bof_signal_count INTEGER DEFAULT 0,
                value_score REAL DEFAULT 0,
                save_decision TEXT,
                twelvelabs_queued INTEGER DEFAULT 0
            );
            """
        )
        conn.execute(
            """
            INSERT INTO creators (
                handle, platform, followers, bio, source, source_hashtag, priority_score,
                total_reels_saved, total_outliers, avg_value_score, best_reel_views, is_active, skip_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "@ugcqueen",
                "instagram",
                85000,
                "UGC creator",
                "hashtag_discovery",
                "skincare",
                91.5,
                4,
                2,
                52.2,
                350000,
                1,
                None,
            ),
        )
        conn.executemany(
            """
            INSERT INTO discovered_content (
                creator_handle, reel_url, view_count, like_count, comment_count,
                creator_followers, audio_name, posted_date, content_tier, hook_pattern,
                likely_bof, bof_signal_count, value_score, save_decision, twelvelabs_queued
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "@ugcqueen",
                    "https://www.instagram.com/reel/AAA111/",
                    350000,
                    22000,
                    600,
                    85000,
                    "Song A",
                    "April 1, 2026",
                    "BOF",
                    "shock_curiosity",
                    1,
                    3,
                    61.0,
                    "save_for_analysis",
                    1,
                ),
                (
                    "@ugcqueen",
                    "https://www.instagram.com/reel/BBB222/",
                    120000,
                    9000,
                    120,
                    85000,
                    "Song B",
                    "April 2, 2026",
                    "MOF",
                    "tutorial",
                    0,
                    1,
                    32.0,
                    "save_metadata",
                    0,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_load_instascrape_snapshot_and_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "discovery.db"
    _seed_instascrape_db(db_path)

    snapshot = load_instascrape_snapshot(db_path)
    assert len(snapshot.creators) == 1
    assert snapshot.creators[0].handle == "@ugcqueen"
    assert len(snapshot.reels) == 2
    assert snapshot.reels[0].reel_url.endswith("/AAA111/")

    queued = load_reel_surface_metrics_from_instascrape(db_path, only_analysis_queue=True)
    assert [row.reel_id for row in queued] == ["AAA111"]

    filtered = load_reel_surface_metrics_from_instascrape(db_path, min_value_score=40.0)
    assert [row.reel_id for row in filtered] == ["AAA111"]


@pytest.mark.asyncio
async def test_reel_discovery_pipeline_uses_instascrape_seed_metrics(tmp_path: Path) -> None:
    db_path = tmp_path / "discovery.db"
    _seed_instascrape_db(db_path)

    templates = MemoryTemplateStore()
    pipeline = ReelDiscoveryPipeline(
        browser=BrowserProviderFacade(MockProvider(dry_run=True)),
        video_understanding=TwelveLabsUnderstanding(dry_run=True),
        templates=templates,
        reel_sink=MemoryReelSink(),
        gemini=GeminiTemplateAgent(dry_run=True),
        download_dir=tmp_path / "downloads",
        seed_metrics_loader=make_instascrape_metrics_loader(db_path, only_analysis_queue=True),
    )

    created = await pipeline.run_discovery_cycle()

    assert len(created) == 1
    assert templates.list_templates()
    assert (tmp_path / "downloads" / "AAA111.mp4").exists()


@pytest.mark.asyncio
async def test_reel_discovery_prefers_video_download_url(monkeypatch, tmp_path: Path) -> None:
    requested: list[str] = []

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            _ = kwargs

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            _ = (exc_type, exc, tb)

        async def get(self, url: str) -> Response:
            requested.append(url)
            return Response(200, content=b"real-mp4-bytes", request=Request("GET", url))

    monkeypatch.setattr(reel_discovery_module.httpx, "AsyncClient", FakeAsyncClient)

    templates = MemoryTemplateStore()
    pipeline = ReelDiscoveryPipeline(
        browser=BrowserProviderFacade(MockProvider(dry_run=True)),
        video_understanding=TwelveLabsUnderstanding(dry_run=True),
        templates=templates,
        reel_sink=MemoryReelSink(),
        gemini=GeminiTemplateAgent(dry_run=True),
        download_dir=tmp_path / "downloads",
        seed_metrics_loader=lambda: [
            reel_discovery_module.ReelSurfaceMetrics(
                reel_id="reel_direct",
                source_url="https://www.instagram.com/reel/reel_direct/",
                video_download_url="https://cdn.example.com/reel_direct.mp4",
                views=50000,
                likes=5000,
                comments=200,
            )
        ],
    )

    created = await pipeline.run_discovery_cycle()

    assert len(created) == 1
    assert requested == ["https://cdn.example.com/reel_direct.mp4"]
    assert (tmp_path / "downloads" / "reel_direct.mp4").read_bytes() == b"real-mp4-bytes"


@pytest.mark.asyncio
async def test_reel_discovery_uses_scrolling_prompt_and_browser_use_metadata(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeBrowser:
        async def run_task(self, task):
            captured["description"] = task.description
            captured["metadata"] = task.metadata
            return AgentResult(
                task_id="task_1",
                success=True,
                provider=ProviderType.BROWSER_USE,
                output={"reels": []},
                dry_run=True,
            )

    templates = MemoryTemplateStore()
    pipeline = ReelDiscoveryPipeline(
        browser=FakeBrowser(),
        video_understanding=TwelveLabsUnderstanding(dry_run=True),
        templates=templates,
        reel_sink=MemoryReelSink(),
        gemini=GeminiTemplateAgent(dry_run=True),
        download_dir=tmp_path / "downloads",
    )

    await pipeline.run_discovery_cycle()

    description = str(captured["description"])
    metadata = captured["metadata"]
    assert "#ugccreator" in description
    assert "creator profiles" in description
    assert "Avoid meme pages, sports clips, celebrities" in description
    assert "Do not finish after inspecting only one creator or one reel" in description
    assert metadata["pipeline"] == "reel_discovery"
    assert metadata["browser_use"]["use_vision"] is True
    assert metadata["browser_use"]["vision_detail_level"] == "high"
    assert metadata["browser_use"]["step_timeout"] == 180


def test_build_reel_discovery_task_supports_custom_hashtag_targets() -> None:
    task = reel_discovery_module._build_reel_discovery_task(
        ReelDiscoverySearchConfig(
            hashtags=["saas", "buildinpublic", "ugccreator"],
            creator_focus_terms=["founder storytelling", "product demo"],
            creator_candidates_to_open=3,
            reel_candidates_to_open=4,
        )
    )

    assert "#saas" in task
    assert "#buildinpublic" in task
    assert "founder storytelling; product demo" in task
    assert "Open up to 3 promising creator profiles" in task
    assert "Open up to 4 of the strongest candidate reels" in task


def test_parse_reels_from_agent_normalizes_counts_and_ignores_extra_fields() -> None:
    result = AgentResult(
        task_id="task_1",
        success=True,
        provider=ProviderType.BROWSER_USE,
        output={
            "final_result": (
                '{"reels":['
                '{"reel_id":"ABC123","source_url":"https://www.instagram.com/reels/ABC123/","video_download_url":null,'
                '"views":0,"likes":"87.5K","comments":"249","creator":"pudgypenguins"},'
                '{"reel_id":"XYZ999","source_url":"https://www.instagram.com/reels/XYZ999/","video_download_url":null,'
                '"views":"1.2M","likes":"810K","comments":"4,905"}'
                "]} "
            )
        },
        dry_run=False,
    )

    rows = reel_discovery_module._parse_reels_from_agent(result)

    assert [row.reel_id for row in rows] == ["ABC123", "XYZ999"]
    assert rows[0].likes == 87500
    assert rows[0].comments == 249
    assert rows[1].views == 1200000
    assert rows[1].likes == 810000
