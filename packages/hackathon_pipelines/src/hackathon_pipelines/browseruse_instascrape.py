"""Bridge the standalone `browseruseinstascrape` prototype into hackathon contracts."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from hackathon_pipelines.contracts import ReelSurfaceMetrics


class InstascrapeCreatorRecord(BaseModel):
    """Typed view of a creator row from the standalone Instagram discovery DB."""

    model_config = ConfigDict(extra="forbid")

    handle: str
    platform: str = "instagram"
    followers: int = Field(default=0, ge=0)
    bio: str | None = None
    source: str | None = None
    source_hashtag: str | None = None
    priority_score: float = 0.0
    total_reels_saved: int = 0
    total_outliers: int = 0
    avg_value_score: float = 0.0
    best_reel_views: int = 0
    is_active: bool = True
    skip_reason: str | None = None


class InstascrapeReelRecord(BaseModel):
    """Typed view of a discovered Instagram reel from the prototype DB."""

    model_config = ConfigDict(extra="forbid")

    creator_handle: str
    reel_url: str
    view_count: int = Field(default=0, ge=0)
    like_count: int = Field(default=0, ge=0)
    comment_count: int = Field(default=0, ge=0)
    creator_followers: int = Field(default=0, ge=0)
    audio_name: str | None = None
    posted_date: str | None = None
    content_tier: str | None = None
    hook_pattern: str | None = None
    likely_bof: bool = False
    bof_signal_count: int = 0
    value_score: float = 0.0
    save_decision: str | None = None
    twelvelabs_queued: bool = False

    def to_surface_metrics(self) -> ReelSurfaceMetrics:
        return ReelSurfaceMetrics(
            reel_id=_reel_id_from_url(self.reel_url),
            source_url=self.reel_url,
            views=self.view_count,
            likes=self.like_count,
            comments=self.comment_count,
        )


class InstascrapeSnapshot(BaseModel):
    """In-memory representation of the standalone discovery DB contents."""

    model_config = ConfigDict(extra="forbid")

    creators: list[InstascrapeCreatorRecord] = Field(default_factory=list)
    reels: list[InstascrapeReelRecord] = Field(default_factory=list)


def _boolish(value: object) -> bool:
    return bool(int(value)) if isinstance(value, (bool, int)) else bool(value)


def _reel_id_from_url(reel_url: str) -> str:
    path = urlparse(reel_url).path.strip("/")
    parts = [part for part in path.split("/") if part]
    if parts:
        return parts[-1]
    return reel_url.rstrip("/").rsplit("/", maxsplit=1)[-1]


def load_instascrape_snapshot(db_path: str | Path) -> InstascrapeSnapshot:
    """Load the standalone `browseruseinstascrape` SQLite DB into typed records."""

    resolved = Path(db_path)
    if not resolved.exists():
        raise FileNotFoundError(resolved)

    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    try:
        creators = [
            InstascrapeCreatorRecord.model_validate(
                {
                    "handle": row["handle"],
                    "platform": row["platform"] or "instagram",
                    "followers": row["followers"] or 0,
                    "bio": row["bio"],
                    "source": row["source"],
                    "source_hashtag": row["source_hashtag"],
                    "priority_score": row["priority_score"] or 0.0,
                    "total_reels_saved": row["total_reels_saved"] or 0,
                    "total_outliers": row["total_outliers"] or 0,
                    "avg_value_score": row["avg_value_score"] or 0.0,
                    "best_reel_views": row["best_reel_views"] or 0,
                    "is_active": _boolish(row["is_active"]),
                    "skip_reason": row["skip_reason"],
                }
            )
            for row in conn.execute(
                """
                SELECT handle, platform, followers, bio, source, source_hashtag,
                       priority_score, total_reels_saved, total_outliers,
                       avg_value_score, best_reel_views, is_active, skip_reason
                FROM creators
                ORDER BY priority_score DESC, handle ASC
                """
            ).fetchall()
        ]

        reels = [
            InstascrapeReelRecord.model_validate(
                {
                    "creator_handle": row["creator_handle"],
                    "reel_url": row["reel_url"],
                    "view_count": row["view_count"] or 0,
                    "like_count": row["like_count"] or 0,
                    "comment_count": row["comment_count"] or 0,
                    "creator_followers": row["creator_followers"] or 0,
                    "audio_name": row["audio_name"],
                    "posted_date": row["posted_date"],
                    "content_tier": row["content_tier"],
                    "hook_pattern": row["hook_pattern"],
                    "likely_bof": _boolish(row["likely_bof"]),
                    "bof_signal_count": row["bof_signal_count"] or 0,
                    "value_score": row["value_score"] or 0.0,
                    "save_decision": row["save_decision"],
                    "twelvelabs_queued": _boolish(row["twelvelabs_queued"]),
                }
            )
            for row in conn.execute(
                """
                SELECT creator_handle, reel_url, view_count, like_count, comment_count,
                       creator_followers, audio_name, posted_date, content_tier,
                       hook_pattern, likely_bof, bof_signal_count, value_score,
                       save_decision, twelvelabs_queued
                FROM discovered_content
                ORDER BY value_score DESC, view_count DESC, reel_url ASC
                """
            ).fetchall()
        ]
    finally:
        conn.close()

    return InstascrapeSnapshot(creators=creators, reels=reels)


def load_reel_surface_metrics_from_instascrape(
    db_path: str | Path,
    *,
    min_value_score: float = 0.0,
    only_analysis_queue: bool = False,
) -> list[ReelSurfaceMetrics]:
    """Convert prototype DB rows into the reel metrics consumed by hackathon pipelines."""

    snapshot = load_instascrape_snapshot(db_path)
    rows = snapshot.reels
    if min_value_score > 0:
        rows = [row for row in rows if row.value_score >= min_value_score]
    if only_analysis_queue:
        rows = [row for row in rows if row.twelvelabs_queued]
    return [row.to_surface_metrics() for row in rows]


def make_instascrape_metrics_loader(
    db_path: str | Path,
    *,
    min_value_score: float = 0.0,
    only_analysis_queue: bool = False,
) -> Callable[[], list[ReelSurfaceMetrics]]:
    """Build a lazy loader suitable for `ReelDiscoveryPipeline(seed_metrics_loader=...)`."""

    def _load() -> list[ReelSurfaceMetrics]:
        return load_reel_surface_metrics_from_instascrape(
            db_path,
            min_value_score=min_value_score,
            only_analysis_queue=only_analysis_queue,
        )

    return _load
