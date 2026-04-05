from __future__ import annotations

import asyncio
from pathlib import Path

from hackathon_pipelines.contracts import VideoStructureRecord
from hackathon_pipelines.local_video_structure_db import seed_video_structure_db_from_local_folder
from hackathon_pipelines.ports import VideoUnderstandingPort
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore


class FakeVideoUnderstanding(VideoUnderstandingPort):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze_reel_file(self, local_video_path: str, *, reel_id: str) -> VideoStructureRecord:
        self.calls.append(Path(local_video_path).name)
        return VideoStructureRecord(
            record_id=f"struct_{reel_id}",
            source_reel_id=reel_id,
            major_scenes=[Path(local_video_path).stem],
            hook_pattern="hook",
            audio_music_cues="audio",
            visual_style="ugc",
            sequence_description="sequence",
            on_screen_text_notes="text",
            raw_analysis_text='{"ok": true}',
        )


class RateLimitedVideoUnderstanding(VideoUnderstandingPort):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze_reel_file(self, local_video_path: str, *, reel_id: str) -> VideoStructureRecord:
        self.calls.append(Path(local_video_path).name)
        if len(self.calls) == 1:
            msg = (
                "headers: {}, status_code: 429, body: {'code': 'too_many_requests', "
                "'message': 'You have exceeded the rate limit (50req/1day). "
                "Please try again later after 2026-04-06T00:41:10Z.'}"
            )
            raise RuntimeError(msg)
        return VideoStructureRecord(
            record_id=f"struct_{reel_id}",
            source_reel_id=reel_id,
            major_scenes=[Path(local_video_path).stem],
            hook_pattern="hook",
            audio_music_cues="audio",
            visual_style="ugc",
            sequence_description="sequence",
            on_screen_text_notes="text",
            raw_analysis_text='{"ok": true}',
        )


def test_seed_video_structure_db_from_local_folder_processes_selected_video_first(tmp_path: Path) -> None:
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    for name in ("test_video1.mp4", "test_video2.mp4", "test_video3.mp4"):
        (video_dir / name).write_bytes(b"fake-mp4")

    db_path = tmp_path / "local.sqlite3"
    fake_video_understanding = FakeVideoUnderstanding()

    result = asyncio.run(
        seed_video_structure_db_from_local_folder(
            video_dir=video_dir,
            db_path=db_path,
            video_understanding=fake_video_understanding,
            selected_video_name="test_video2.mp4",
        )
    )

    store = SQLiteHackathonStore(db_path)
    selected_metric = store.get_reel_metric("local_test_video2_mp4")

    assert fake_video_understanding.calls == ["test_video2.mp4", "test_video1.mp4", "test_video3.mp4"]
    assert result.processed_reel_ids == [
        "local_test_video2_mp4",
        "local_test_video1_mp4",
        "local_test_video3_mp4",
    ]
    assert selected_metric is not None
    assert selected_metric.is_ugc_candidate is True
    assert selected_metric.ugc_reason == "preselected_local_seed"
    assert result.selected_video_name == "test_video2.mp4"
    assert len(store.list_structures()) == 3


def test_seed_video_structure_db_from_local_folder_skips_existing_structures(tmp_path: Path) -> None:
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    for name in ("test_video1.mp4", "test_video2.mp4"):
        (video_dir / name).write_bytes(b"fake-mp4")

    db_path = tmp_path / "local.sqlite3"
    store = SQLiteHackathonStore(db_path)
    store.save_structure(
        VideoStructureRecord(
            record_id="struct_existing",
            source_reel_id="local_test_video1_mp4",
            major_scenes=["existing"],
            hook_pattern="hook",
            audio_music_cues="audio",
            visual_style="ugc",
            sequence_description="sequence",
            on_screen_text_notes="text",
            raw_analysis_text='{"ok": true}',
        )
    )

    fake_video_understanding = FakeVideoUnderstanding()
    result = asyncio.run(
        seed_video_structure_db_from_local_folder(
            video_dir=video_dir,
            db_path=db_path,
            video_understanding=fake_video_understanding,
        )
    )

    assert fake_video_understanding.calls == ["test_video2.mp4"]
    assert result.skipped_reel_ids == ["local_test_video1_mp4"]
    assert result.processed_reel_ids == ["local_test_video2_mp4"]
    assert result.selected_video_name == "test_video1.mp4"


def test_seed_video_structure_db_from_local_folder_stops_after_rate_limit(tmp_path: Path) -> None:
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    for name in ("test_video1.mp4", "test_video2.mp4", "test_video3.mp4"):
        (video_dir / name).write_bytes(b"fake-mp4")

    db_path = tmp_path / "local.sqlite3"
    rate_limited_video_understanding = RateLimitedVideoUnderstanding()
    result = asyncio.run(
        seed_video_structure_db_from_local_folder(
            video_dir=video_dir,
            db_path=db_path,
            video_understanding=rate_limited_video_understanding,
        )
    )

    store = SQLiteHackathonStore(db_path)

    assert rate_limited_video_understanding.calls == ["test_video1.mp4"]
    assert result.processed_reel_ids == []
    assert result.halted_due_to_rate_limit is True
    assert result.resume_after == "2026-04-06T00:41:10Z"
    assert len(result.error_messages) == 1
    assert "Resume after 2026-04-06T00:41:10Z." in result.error_messages[0]
    assert len(store.list_structures()) == 0
