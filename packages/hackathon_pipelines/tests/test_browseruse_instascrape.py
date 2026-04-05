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
    captured_tasks: list[object] = []

    class FakeBrowser:
        async def run_task(self, task):
            captured_tasks.append(task)
            return AgentResult(
                task_id=f"task_{len(captured_tasks)}",
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

    assert len(captured_tasks) == 1
    description = str(captured_tasks[0].description)
    url = captured_tasks[0].url
    metadata = captured_tasks[0].metadata
    assert "go directly to https://www.instagram.com/reels/" in description
    assert "As soon as you have 5 good unique reels, stop" in description
    assert "Avoid meme pages, sports clips, celebrities" in description
    assert "This is a hackathon demo, so keep discovery simple and reliable." in description
    assert "NEVER use search engines" in description
    assert "NEVER open downloader sites" in description
    assert "Downloading happens later through the API/downloader pipeline outside the browser." in description
    assert "NEVER click creator profiles" in description
    assert "is_ugc_candidate" in description
    assert url == reel_discovery_module.INSTAGRAM_REELS_FEED_URL
    assert metadata["browser_use_output_model_schema"] is reel_discovery_module.BrowserUseDiscoveredReels
    assert metadata["pipeline"] == "reel_discovery"
    assert metadata["browser_use"]["use_vision"] is True
    assert metadata["browser_use"]["vision_detail_level"] == "high"
    assert metadata["browser_use"]["step_timeout"] == 180
    assert "Do not open search engines such as DuckDuckGo" in metadata["browser_use"]["extend_system_message"]
    assert "do not visit downloader sites" in metadata["browser_use"]["extend_system_message"]
    assert [task.metadata["discovery_agent_index"] for task in captured_tasks] == [0]
    assert all(task.metadata["discovery_agent_count"] == 1 for task in captured_tasks)


def test_build_reel_discovery_task_supports_custom_hashtag_targets() -> None:
    task = reel_discovery_module._build_reel_discovery_task(
        ReelDiscoverySearchConfig(
            discovery_mode="hashtag_profiles",
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
    assert "Do not use DuckDuckGo, Google, Bing, or any downloader website." in task
    assert "Discovery is metadata only." in task


def test_build_reel_discovery_task_feed_scroll_mode_targets_five_good_reels() -> None:
    task = reel_discovery_module._build_reel_discovery_task(
        ReelDiscoverySearchConfig(
            discovery_mode="feed_scroll",
            creator_focus_terms=["product demo", "testimonial"],
            target_good_reels=5,
        )
    )

    assert "go directly to https://www.instagram.com/reels/" in task
    assert "Scroll through Reels until you find 5 strong creator-style reels" in task
    assert "product demo; testimonial" in task
    assert "As soon as you have 5 good unique reels, stop" in task
    assert "NEVER search for 'instagram reel downloader'" in task
    assert "Downloading happens later through the API/downloader pipeline outside the browser." in task
    assert "NEVER click creator profiles" in task
    assert "ugc_reason" in task


@pytest.mark.asyncio
async def test_reel_discovery_requires_external_downloader_when_no_media_url(tmp_path: Path) -> None:
    class FakeBrowser:
        async def run_task(self, task):
            return AgentResult(
                task_id="task_missing_media_url",
                success=True,
                provider=ProviderType.BROWSER_USE,
                output={
                    "reels": [
                        {
                            "reel_id": "reel_no_url",
                            "source_url": "https://www.instagram.com/reel/reel_no_url/",
                            "views": 50000,
                            "likes": 5000,
                            "comments": 200,
                        }
                    ]
                },
                dry_run=False,
            )

    pipeline = ReelDiscoveryPipeline(
        browser=FakeBrowser(),
        video_understanding=TwelveLabsUnderstanding(dry_run=True),
        templates=MemoryTemplateStore(),
        reel_sink=MemoryReelSink(),
        gemini=GeminiTemplateAgent(dry_run=True),
        download_dir=tmp_path / "downloads",
    )

    with pytest.raises(RuntimeError, match="use the API/Instaloader download stage instead of Browser Use"):
        await pipeline.run_discovery_cycle()


@pytest.mark.asyncio
async def test_reel_discovery_pipeline_merges_duplicate_reels_across_parallel_workers(tmp_path: Path) -> None:
    payloads = [
        [
            {
                "reel_id": "AAA111",
                "source_url": "https://www.instagram.com/reel/AAA111/",
                "views": 21000,
                "likes": 700,
                "comments": 32,
                "is_ugc_candidate": True,
                "ugc_reason": "worker 1",
            }
        ],
    ]

    class FakeBrowser:
        def __init__(self) -> None:
            self.calls = 0

        async def run_task(self, task):
            self.calls += 1
            return AgentResult(
                task_id=f"task_{self.calls}",
                success=True,
                provider=ProviderType.BROWSER_USE,
                output={"reels": payloads[self.calls - 1]},
                dry_run=True,
            )

    reel_sink = MemoryReelSink()
    pipeline = ReelDiscoveryPipeline(
        browser=FakeBrowser(),
        video_understanding=TwelveLabsUnderstanding(dry_run=True),
        templates=MemoryTemplateStore(),
        reel_sink=reel_sink,
        gemini=GeminiTemplateAgent(dry_run=True),
        download_dir=tmp_path / "downloads",
    )

    await pipeline.run_discovery_cycle()

    rows = {row.reel_id: row for row in reel_sink.rows}
    assert set(rows) == {"AAA111"}
    assert rows["AAA111"].likes == 700
    assert rows["AAA111"].comments == 32
    assert rows["AAA111"].views == 21000
    assert rows["AAA111"].creator_handle is None


@pytest.mark.asyncio
async def test_run_parallel_reel_discovery_can_launch_separate_worker_windows_without_cdp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cloned_targets: list[Path] = []
    launched_ports: list[int] = []
    built_cdp_urls: list[str] = []
    processes: list[object] = []

    class FakePrimaryBrowser:
        def __init__(self) -> None:
            self.calls: list[object] = []

        async def run_task(self, task):
            self.calls.append(task)
            return AgentResult(
                task_id="primary_task",
                success=True,
                provider=ProviderType.BROWSER_USE,
                output={
                    "reels": [
                        {
                            "reel_id": "PRIMARY111",
                            "source_url": "https://www.instagram.com/reel/PRIMARY111/",
                            "views": 25000,
                            "likes": 1400,
                            "comments": 90,
                            "is_ugc_candidate": True,
                        }
                    ]
                },
                dry_run=False,
            )

    class FakeExtraBrowser:
        def __init__(self, suffix: str) -> None:
            self.suffix = suffix
            self.calls: list[object] = []

        async def run_task(self, task):
            self.calls.append(task)
            return AgentResult(
                task_id=f"extra_{self.suffix}",
                success=True,
                provider=ProviderType.BROWSER_USE,
                output={
                    "reels": [
                        {
                            "reel_id": f"EXTRA{self.suffix}",
                            "source_url": f"https://www.instagram.com/reel/EXTRA{self.suffix}/",
                            "views": 18000,
                            "likes": 900,
                            "comments": 55,
                            "is_ugc_candidate": True,
                        }
                    ]
                },
                dry_run=False,
            )

    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    extra_browsers: list[FakeExtraBrowser] = []

    def fake_ensure_profile_clone(**kwargs):
        target = Path(kwargs["target_user_data_dir"])
        cloned_targets.append(target)
        return target

    monkeypatch.setattr(
        reel_discovery_module,
        "ensure_profile_clone",
        fake_ensure_profile_clone,
    )
    monkeypatch.setattr(reel_discovery_module, "_find_free_local_port", lambda start_port: start_port)

    async def fake_launch_local_debug_chrome(**kwargs):
        launched_ports.append(kwargs["cdp_port"])
        process = FakeProcess()
        processes.append(process)
        return process, f"http://127.0.0.1:{kwargs['cdp_port']}"

    monkeypatch.setattr(reel_discovery_module, "launch_local_debug_chrome", fake_launch_local_debug_chrome)

    def fake_build_browser_port_for_cdp(cdp_url: str):
        built_cdp_urls.append(cdp_url)
        browser = FakeExtraBrowser(str(len(extra_browsers) + 2))
        extra_browsers.append(browser)
        return browser

    monkeypatch.setattr(reel_discovery_module, "_build_browser_port_for_cdp", fake_build_browser_port_for_cdp)

    metrics, results = await reel_discovery_module.run_parallel_reel_discovery(
        browser=FakePrimaryBrowser(),
        search_config=ReelDiscoverySearchConfig(
            discovery_mode="feed_scroll",
            target_good_reels=5,
        ),
        max_steps=10,
        agent_count=3,
        browser_runtime_env={
            "CHROME_EXECUTABLE_PATH": "/usr/bin/google-chrome",
            "CHROME_USER_DATA_DIR": str(tmp_path / "source_user_data"),
            "CHROME_PROFILE_DIRECTORY": "Profile 9",
            "BROWSER_USE_HEADLESS": "false",
        },
    )

    assert len(results) == 3
    assert {metric.reel_id for metric in metrics} == {"EXTRA2", "EXTRA3", "EXTRA4"}
    assert len(cloned_targets) == 3
    assert launched_ports == [9222, 9223, 9224]
    assert built_cdp_urls == [
        "http://127.0.0.1:9222",
        "http://127.0.0.1:9223",
        "http://127.0.0.1:9224",
    ]
    assert len(extra_browsers) == 3
    assert all(process.terminated for process in processes)


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


def test_parse_reels_from_agent_extracts_embedded_json_from_prose() -> None:
    result = AgentResult(
        task_id="task_embedded_json",
        success=True,
        provider=ProviderType.BROWSER_USE,
        output={
            "final_result": (
                "Successfully found 5 creator-style reels.\n\n"
                'Final JSON:\n{"reels":['
                '{"reel_id":"DR4f1p8jgIg","source_url":"https://www.instagram.com/reels/DR4f1p8jgIg/",'
                '"video_download_url":"blob:https://www.instagram.com/demo","views":null,"likes":"3,652","comments":"151"},'
                '{"reel_id":"DUWIKN2jfSw","source_url":"https://www.instagram.com/reels/DUWIKN2jfSw/",'
                '"video_download_url":null,"views":"0","likes":"5,993","comments":"97"}'
                "]}"
            )
        },
        dry_run=False,
    )

    rows = reel_discovery_module._parse_reels_from_agent(result)

    assert [row.reel_id for row in rows] == ["DR4f1p8jgIg", "DUWIKN2jfSw"]
    assert rows[0].video_download_url is None
    assert rows[0].likes == 3652
    assert rows[0].comments == 151
    assert rows[0].views == 0
    assert rows[1].likes == 5993


def test_parse_reels_from_agent_extracts_escaped_json_from_done_text() -> None:
    result = AgentResult(
        task_id="task_escaped_json",
        success=True,
        provider=ProviderType.BROWSER_USE,
        output={
            "final_result": (
                '{\\"reels\\":[{\\"reel_id\\":\\"DS3r5H-jvF1\\",'
                '\\"source_url\\":\\"https://www.instagram.com/reels/DS3r5H-jvF1/\\",'
                '\\"video_download_url\\":null,\\"views\\":0,\\"likes\\":40500,\\"comments\\":395}]}'
            )
        },
        dry_run=False,
    )

    rows = reel_discovery_module._parse_reels_from_agent(result)

    assert [row.reel_id for row in rows] == ["DS3r5H-jvF1"]
    assert rows[0].likes == 40500
    assert rows[0].comments == 395


def test_parse_reels_from_agent_rejects_non_video_download_urls() -> None:
    result = AgentResult(
        task_id="task_2",
        success=True,
        provider=ProviderType.BROWSER_USE,
        output={
            "reels": [
                {
                    "reel_id": "CSS123",
                    "source_url": "https://www.instagram.com/reels/CSS123/",
                    "video_download_url": "https://static.cdninstagram.com/rsrc.php/v5/yV/l/example.css",
                    "views": 0,
                    "likes": 10,
                    "comments": 1,
                },
                {
                    "reel_id": "MP4123",
                    "source_url": "https://www.instagram.com/reels/MP4123/",
                    "video_download_url": "https://cdn.example.com/video_versions/abc123?mime_type=video_mp4",
                    "views": 0,
                    "likes": 11,
                    "comments": 2,
                },
            ]
        },
        dry_run=False,
    )

    rows = reel_discovery_module._parse_reels_from_agent(result)

    assert [row.reel_id for row in rows] == ["CSS123", "MP4123"]
    assert rows[0].video_download_url is None
    assert rows[1].video_download_url == "https://cdn.example.com/video_versions/abc123?mime_type=video_mp4"
