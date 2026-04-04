"""Tests for PostingScheduler."""
from __future__ import annotations

from datetime import datetime

import pytest

from ..contracts import Platform
from ..scheduler import PlatformTarget, PostingScheduler, PostingWindow
from .fixtures import make_package


@pytest.fixture
def scheduler() -> PostingScheduler:
    targets = [
        PlatformTarget(
            platform=Platform.TIKTOK,
            window=PostingWindow(start_hour=0, end_hour=23),
            max_posts_per_day=3,
            priority=5,
        ),
        PlatformTarget(
            platform=Platform.INSTAGRAM,
            window=PostingWindow(start_hour=0, end_hour=23),
            max_posts_per_day=2,
            priority=5,
        ),
    ]
    return PostingScheduler(targets=targets, dry_run=True, sandbox=True)


def test_enqueue_creates_posts_for_all_target_platforms(scheduler: PostingScheduler) -> None:
    package = make_package()
    posts = scheduler.enqueue(package, now=datetime(2026, 4, 4, 12, 0, 0))

    assert len(posts) == 2
    platforms = {p.platform for p in posts}
    assert platforms == {Platform.TIKTOK, Platform.INSTAGRAM}


def test_enqueue_respects_explicit_platform_list(scheduler: PostingScheduler) -> None:
    package = make_package()
    now = datetime(2026, 4, 4, 12, 0, 0)
    posts = scheduler.enqueue(package, platforms=[Platform.TIKTOK], now=now)

    assert len(posts) == 1
    assert posts[0].platform == Platform.TIKTOK


def test_enqueue_skips_unconfigured_platform(scheduler: PostingScheduler) -> None:
    package = make_package(target_platforms=[Platform.YOUTUBE])
    posts = scheduler.enqueue(package, now=datetime(2026, 4, 4, 12, 0, 0))

    assert posts == []


def test_enqueue_respects_daily_limit(scheduler: PostingScheduler) -> None:
    package = make_package(target_platforms=[Platform.INSTAGRAM])
    now = datetime(2026, 4, 4, 12, 0, 0)

    # Fill up the daily limit (2 for Instagram)
    for _ in range(2):
        posts = scheduler.enqueue(package, now=now)
        for p in posts:
            scheduler.mark_done(p.post_id)

    # Third enqueue should be skipped
    posts = scheduler.enqueue(package, now=now)
    assert posts == []


def test_dequeue_ready_returns_queued_posts_within_window(scheduler: PostingScheduler) -> None:
    package = make_package()
    now = datetime(2026, 4, 4, 12, 0, 0)
    scheduler.enqueue(package, now=now)

    ready = scheduler.dequeue_ready(now=now)
    assert len(ready) == 2
    assert all(p.status == "executing" for p in ready)


def test_dequeue_ready_excludes_posts_outside_window() -> None:
    targets = [
        PlatformTarget(
            platform=Platform.TIKTOK,
            window=PostingWindow(start_hour=14, end_hour=20),
            max_posts_per_day=5,
        )
    ]
    scheduler = PostingScheduler(targets=targets, dry_run=True)
    package = make_package(target_platforms=[Platform.TIKTOK])
    now = datetime(2026, 4, 4, 8, 0, 0)  # 08:00 — before window starts at 14:00
    scheduler.enqueue(package, now=now)

    ready = scheduler.dequeue_ready(now=now)
    assert ready == []


def test_mark_done_updates_status(scheduler: PostingScheduler) -> None:
    package = make_package(target_platforms=[Platform.TIKTOK])
    posts = scheduler.enqueue(package, now=datetime(2026, 4, 4, 12, 0, 0))
    post = posts[0]
    scheduler.dequeue_ready(now=datetime(2026, 4, 4, 12, 0, 0))

    scheduler.mark_done(post.post_id, record_id="rec-001")

    snapshot = scheduler.queue_snapshot()
    done = next(p for p in snapshot if p.post_id == post.post_id)
    assert done.status == "done"
    assert done.result_record_id == "rec-001"


def test_mark_failed_updates_status(scheduler: PostingScheduler) -> None:
    package = make_package(target_platforms=[Platform.TIKTOK])
    posts = scheduler.enqueue(package, now=datetime(2026, 4, 4, 12, 0, 0))
    post = posts[0]
    scheduler.dequeue_ready(now=datetime(2026, 4, 4, 12, 0, 0))

    scheduler.mark_failed(post.post_id, error="network timeout")

    snapshot = scheduler.queue_snapshot()
    failed = next(p for p in snapshot if p.post_id == post.post_id)
    assert failed.status == "failed"


def test_is_within_window_true(scheduler: PostingScheduler) -> None:
    now = datetime(2026, 4, 4, 15, 0, 0)  # 15:00, Mon–Sun window
    assert scheduler.is_within_window(Platform.TIKTOK, now) is True


def test_is_within_window_false_hour(scheduler: PostingScheduler) -> None:
    targets = [
        PlatformTarget(
            platform=Platform.TIKTOK,
            window=PostingWindow(start_hour=10, end_hour=18),
        )
    ]
    s = PostingScheduler(targets=targets, dry_run=True)
    now = datetime(2026, 4, 4, 9, 0, 0)
    assert s.is_within_window(Platform.TIKTOK, now) is False


def test_queue_snapshot_is_independent_copy(scheduler: PostingScheduler) -> None:
    package = make_package()
    scheduler.enqueue(package, now=datetime(2026, 4, 4, 12, 0, 0))

    snap1 = scheduler.queue_snapshot()
    scheduler.enqueue(make_package(title="Another"), now=datetime(2026, 4, 4, 12, 0, 0))
    snap2 = scheduler.queue_snapshot()

    # snap1 was taken before the second enqueue so it's shorter
    assert len(snap2) > len(snap1)
