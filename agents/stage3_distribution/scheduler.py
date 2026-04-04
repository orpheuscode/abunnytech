"""
PostingScheduler — manages a priority queue of scheduled social-media posts.

No persistence here; the queue lives in memory. Write/read to disk is handled
by persistence.py (separate concern).
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Literal

from browser_runtime.audit import get_audit
from pydantic import BaseModel, Field

from .contracts import ContentPackage, Platform

_SCHEDULER_NAME = "posting_scheduler"


# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------


class PostingWindow(BaseModel):
    start_hour: int  # 0–23 UTC, inclusive
    end_hour: int    # 0–23 UTC, inclusive
    days_of_week: list[int] = [0, 1, 2, 3, 4, 5, 6]  # 0 = Monday (ISO weekday - 1)


class PlatformTarget(BaseModel):
    platform: Platform
    window: PostingWindow = Field(
        default_factory=lambda: PostingWindow(start_hour=8, end_hour=22)
    )
    max_posts_per_day: int = 3
    priority: int = 5  # lower value = higher priority


class ScheduledPost(BaseModel):
    post_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    package: ContentPackage
    platform: Platform
    scheduled_at: datetime
    priority: int = 5
    status: Literal["queued", "executing", "done", "failed", "skipped"] = "queued"
    result_record_id: str | None = None


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class PostingScheduler:
    """
    Priority queue for scheduled posts.

    Posts are ordered by (priority ASC, scheduled_at ASC). The scheduler does
    not execute posts — that's PostingExecutor's job.
    """

    def __init__(
        self,
        targets: list[PlatformTarget],
        dry_run: bool = True,
        sandbox: bool = True,
    ) -> None:
        self._targets: dict[Platform, PlatformTarget] = {t.platform: t for t in targets}
        self._dry_run = dry_run
        self._sandbox = sandbox
        self._queue: list[ScheduledPost] = []

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        package: ContentPackage,
        platforms: list[Platform] | None = None,
        now: datetime | None = None,
    ) -> list[ScheduledPost]:
        """
        Create a ScheduledPost for each target platform.

        If `platforms` is None, falls back to package.target_platforms filtered
        to platforms that have a PlatformTarget configured on this scheduler.
        Respects max_posts_per_day — silently skips platforms that have hit
        their daily ceiling.
        """
        now = now or datetime.now(UTC)
        audit = get_audit()
        target_platforms = platforms if platforms is not None else package.target_platforms
        # Only schedule for platforms this scheduler has config for
        target_platforms = [p for p in target_platforms if p in self._targets]

        created: list[ScheduledPost] = []
        for platform in target_platforms:
            target = self._targets[platform]
            if self.daily_post_count(platform, now.date()) >= target.max_posts_per_day:
                audit.log(
                    f"{_SCHEDULER_NAME}.enqueue.skipped",
                    {
                        "package_id": package.package_id,
                        "platform": platform.value,
                        "reason": "daily_limit_reached",
                        "dry_run": self._dry_run,
                    },
                    level="WARNING",
                )
                continue

            post = ScheduledPost(
                package=package,
                platform=platform,
                scheduled_at=now,
                priority=min(package.priority, target.priority),
            )
            self._queue.append(post)
            audit.log(
                f"{_SCHEDULER_NAME}.enqueue",
                {
                    "post_id": post.post_id,
                    "package_id": package.package_id,
                    "platform": platform.value,
                    "scheduled_at": post.scheduled_at.isoformat(),
                    "priority": post.priority,
                    "dry_run": self._dry_run,
                },
            )
            created.append(post)

        return created

    # ------------------------------------------------------------------
    # Dequeue
    # ------------------------------------------------------------------

    def dequeue_ready(self, now: datetime | None = None) -> list[ScheduledPost]:
        """
        Return all queued posts that are ready to execute right now.

        A post is ready when:
        - status == "queued"
        - scheduled_at <= now
        - current UTC hour is within the platform's posting window
        - the platform has not yet hit its daily post limit (counting "done" posts)

        Ready posts are marked "executing" in-place before being returned.
        """
        now = now or datetime.now(UTC)
        audit = get_audit()
        ready: list[ScheduledPost] = []

        # Sort by priority then scheduled_at so callers get them in correct order
        candidates = sorted(
            (p for p in self._queue if p.status == "queued" and p.scheduled_at <= now),
            key=lambda p: (p.priority, p.scheduled_at),
        )

        for post in candidates:
            if not self.is_within_window(post.platform, now):
                continue
            target = self._targets.get(post.platform)
            at_daily_limit = (
                target is not None
                and self.daily_post_count(post.platform, now.date()) >= target.max_posts_per_day
            )
            if at_daily_limit:
                continue
            post.status = "executing"
            audit.log(
                f"{_SCHEDULER_NAME}.dequeue",
                {
                    "post_id": post.post_id,
                    "platform": post.platform.value,
                    "dry_run": self._dry_run,
                },
            )
            ready.append(post)

        return ready

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def mark_done(self, post_id: str, record_id: str | None = None) -> None:
        post = self._find(post_id)
        post.status = "done"
        post.result_record_id = record_id
        get_audit().log(
            f"{_SCHEDULER_NAME}.mark_done",
            {"post_id": post_id, "record_id": record_id, "dry_run": self._dry_run},
        )

    def mark_failed(self, post_id: str, error: str) -> None:
        post = self._find(post_id)
        post.status = "failed"
        get_audit().log(
            f"{_SCHEDULER_NAME}.mark_failed",
            {"post_id": post_id, "error": error, "dry_run": self._dry_run},
            level="ERROR",
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_within_window(self, platform: Platform, now: datetime) -> bool:
        """True if the current UTC hour falls inside the platform's posting window."""
        target = self._targets.get(platform)
        if not target:
            return False
        window = target.window
        # days_of_week uses 0=Monday, matching datetime.weekday()
        if now.weekday() not in window.days_of_week:
            return False
        return window.start_hour <= now.hour <= window.end_hour

    def daily_post_count(self, platform: Platform, date: date) -> int:
        """Count posts with status 'done' for the given platform and calendar date (UTC)."""
        return sum(
            1
            for p in self._queue
            if (
                p.platform == platform
                and p.status == "done"
                and p.scheduled_at.date() == date
            )
        )

    def queue_snapshot(self) -> list[ScheduledPost]:
        """Return a shallow copy of the queue (safe for callers to iterate without mutation)."""
        return list(self._queue)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find(self, post_id: str) -> ScheduledPost:
        for post in self._queue:
            if post.post_id == post_id:
                return post
        raise KeyError(f"ScheduledPost not found: {post_id}")
