"""
Canonical Pydantic v2 contract models for Stage 4 Analyze & Adapt.

Consumed contracts (from upstream stages):
    DistributionRecord  — from Stage 3
    ContentPackage      — from Stage 2
    VideoBlueprint      — from Stage 2
    IdentityMatrix      — from Stage 0
    ProductCatalogItem  — from Stage 5

Emitted contracts (to downstream consumers):
    PerformanceMetricRecord     — fed into analytics store + Stage 4 analysis
    OptimizationDirectiveEnvelope — fed back to Stages 1, 2, 3
    RedoQueueItem               — fed back to Stages 1, 2, 3

When packages/contracts is created, these should be replaced with imports.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Upstream contracts (consumed by Stage 4)
# ---------------------------------------------------------------------------


class DistributionRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content_package_id: str
    video_blueprint_id: str | None = None
    platform: str  # "tiktok" | "instagram" | "youtube"
    post_id: str | None = None
    post_url: str | None = None
    posted_at: datetime | None = None
    status: Literal["posted", "scheduled", "failed", "dry_run"] = "posted"
    audio_id: str | None = None
    schedule_slot: str | None = None  # e.g. "tue_18:00"
    dry_run: bool = False


class ContentPackage(BaseModel):
    package_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    video_blueprint_id: str
    hook_text: str = ""
    hook_style: str = "bold_claim"  # "question" | "bold_claim" | "story" | "tutorial"
    content_tier: str = "hub"       # "hero" | "hub" | "hygiene"
    audio_id: str | None = None
    schedule_slot: str | None = None
    platform_targets: list[str] = []


class VideoBlueprint(BaseModel):
    blueprint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hook_style: str = "bold_claim"
    duration_seconds: int = 30
    topic: str = ""
    niche_tags: list[str] = []


class IdentityMatrix(BaseModel):
    identity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    persona_name: str
    niche: str
    platform_targets: list[str] = []
    tone: str = "conversational"
    posting_cadence: dict[str, Any] = {}  # platform → posts/week


class ProductCatalogItem(BaseModel):
    product_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: str
    price_usd: float = 0.0
    commission_rate_pct: float = 0.0
    platform: str = "shopify"
    active: bool = True


# ---------------------------------------------------------------------------
# Emitted contracts (produced by Stage 4)
# ---------------------------------------------------------------------------


class PerformanceMetricRecord(BaseModel):
    """One row of collected analytics for a single post."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    distribution_record_id: str
    post_id: str
    platform: str
    content_package_id: str | None = None
    video_blueprint_id: str | None = None

    # Engagement metrics
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    follows_gained: int = 0

    # Retention / watch-time
    watch_time_avg_seconds: float = 0.0
    completion_rate_pct: float = 0.0     # 0-100
    hook_retention_3s_pct: float = 0.0  # % viewers still watching at 3 s
    hook_retention_50pct: float = 0.0   # % viewers who watched 50 %+

    # Derived / attributed
    engagement_rate_pct: float = 0.0    # (likes+comments+shares+saves)/views × 100
    revenue_attributed: float = 0.0     # USD, from linked product clicks

    # Context tags — used for dimensional slicing
    audio_id: str | None = None
    schedule_slot: str | None = None   # e.g. "tue_18:00"
    content_tier: str | None = None    # "hero" | "hub" | "hygiene"
    hook_style: str | None = None      # "question" | "bold_claim" | "story" | "tutorial"
    product_id: str | None = None      # top product in this video (if any)

    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    source: Literal["platform_api", "browser_extract", "mock"] = "mock"


class OptimizationDirectiveEnvelope(BaseModel):
    """
    A structured, target-stage-specific action directive.

    payload contents vary by directive_type:
      hook_rewrite:      {hook_style: str, example_hooks: list[str], avoid_styles: list[str]}
      schedule_shift:    {current_slot: str, recommended_slot: str, lift_pct: float}
      content_tier_rebalance: {current_ratio: dict, target_ratio: dict}
      audio_swap:        {avoid_audio_ids: list[str], preferred_audio_ids: list[str]}
      product_focus:     {top_product_ids: list[str], drop_product_ids: list[str]}
    """

    envelope_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    analysis_window_days: int = 7
    target_stage: Literal["stage1", "stage2", "stage3", "stage1+stage2"]
    directive_type: Literal[
        "hook_rewrite",
        "schedule_shift",
        "content_tier_rebalance",
        "audio_swap",
        "product_focus",
    ]
    priority: Literal["critical", "high", "medium", "low"]
    rationale: str
    payload: dict[str, Any]
    applies_to_blueprint_ids: list[str] = []
    expires_at: datetime | None = None
    dry_run: bool = False


class RedoQueueItem(BaseModel):
    """
    A post flagged for regeneration after underperformance.

    Feeds back to Stage 1 (re-discover) or Stage 2 (re-generate) or Stage 3 (re-schedule).
    """

    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    queued_at: datetime = Field(default_factory=datetime.utcnow)
    source_distribution_record_id: str
    source_content_package_id: str | None = None
    source_video_blueprint_id: str | None = None

    redo_reason: Literal[
        "underperformed",
        "hook_failed",
        "wrong_schedule",
        "audio_mismatch",
        "low_completion",
    ]
    priority: Literal["critical", "high", "medium", "low"]
    suggested_mutations: dict[str, Any]  # what to change on the regenerated version
    target_stage: Literal["stage1", "stage2", "stage3"]
    retry_count: int = 0
    status: Literal["queued", "in_progress", "done", "skipped"] = "queued"
    dry_run: bool = False
