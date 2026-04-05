from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from browser_runtime.providers.mock import MockProvider

from hackathon_pipelines.adapters.facade import BrowserProviderFacade
from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, TwelveLabsUnderstanding
from hackathon_pipelines.browseruse_instascrape import (
    load_instascrape_snapshot,
    load_reel_surface_metrics_from_instascrape,
    make_instascrape_metrics_loader,
)
from hackathon_pipelines.pipelines.reel_discovery import ReelDiscoveryPipeline
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
