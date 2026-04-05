"""Shared data contracts for Browser Use + TwelveLabs + Gemini/Veo hackathon flows."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TemplateDisposition(StrEnum):
    """How the orchestrator treats a template given history + new signals."""

    REMAKE = "remake"
    ITERATE = "iterate"
    DISCARD = "discard"


class TemplatePerformanceLabel(StrEnum):
    """Feedback loop label after a post has analytics."""

    SUCCESSFUL_REUSE = "successful_reuse"
    REMIXABLE = "remixable"
    WEAK_DISCARD = "weak_discard"


class ReelSurfaceMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reel_id: str
    source_url: str
    video_download_url: str | None = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReelDiscoveryThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_views: int = 10_000
    min_likes: int = 500
    min_comments: int = 20


class VideoStructureRecord(BaseModel):
    """Structured understanding from TwelveLabs (JSON parsed from analyze output)."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    source_reel_id: str
    major_scenes: list[str] = Field(default_factory=list)
    hook_pattern: str | None = None
    audio_music_cues: str | None = None
    visual_style: str | None = None
    sequence_description: str | None = None
    on_screen_text_notes: str | None = None
    raw_analysis_text: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VideoTemplateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    structure_record_id: str
    veo_prompt_draft: str
    disposition: TemplateDisposition = TemplateDisposition.ITERATE
    disposition_reason: str | None = None
    performance_label: TemplatePerformanceLabel | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProductCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    title: str
    source_url: str
    platform: str = "aliexpress"
    visual_marketability: float = Field(ge=0.0, le=1.0, default=0.5)
    popularity_signal: float = Field(ge=0.0, le=1.0, default=0.5)
    content_potential: float = Field(ge=0.0, le=1.0, default=0.5)
    dropship_score: float = Field(ge=0.0, le=1.0, default=0.5)
    notes: str | None = None


class GenerationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    template_id: str
    product_id: str
    veo_prompt: str
    product_title: str = ""
    product_description: str = ""
    creative_brief: str = ""
    product_image_path: str
    avatar_image_path: str
    reference_image_paths: list[str] = Field(default_factory=list)
    prior_template_metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedVideoArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    bundle_id: str
    video_uri: str | None = None
    video_path: str | None = None
    model_id: str
    reference_image_paths: list[str] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PostJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    platform: Literal["instagram"] = "instagram"
    media_path: str
    caption: str
    dry_run: bool = True


class PostAnalyticsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    post_id: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    engagement_trend: str | None = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrchestratorRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    reels_scanned: int = 0
    reels_downloaded: int = 0
    structures_persisted: int = 0
    templates_created: int = 0
    products_ranked: int = 0
    generations: int = 0
    posts: int = 0
    analytics_snapshots: int = 0
    notes: list[str] = Field(default_factory=list)


class ClosedLoopRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    reel_summary: OrchestratorRunSummary
    product_summary: OrchestratorRunSummary
    publish_summary: OrchestratorRunSummary | None = None
    template_id: str | None = None
    product_id: str | None = None
    bundle_id: str | None = None
    artifact_id: str | None = None
    media_path: str | None = None
    notes: list[str] = Field(default_factory=list)
