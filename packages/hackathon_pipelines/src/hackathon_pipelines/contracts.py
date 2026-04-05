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


class CommentCategory(StrEnum):
    """Normalized Instagram comment categories for engagement handling."""

    PURCHASE_INTENT = "purchase_intent"
    QUESTION = "question"
    COMPLIMENT = "compliment"
    CRITICISM = "criticism"
    SPAM = "spam"
    GENERAL = "general"


class CommentEngagementStatus(StrEnum):
    """High-level outcome of a comment engagement scan."""

    NOT_RUN = "not_run"
    SKIPPED = "skipped"
    NO_ACTION_NEEDED = "no_action_needed"
    REPLIED = "replied"
    FAILED = "failed"


class CommentResponseExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    output: str


class CommentEngagementPersona(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_identity_id: str | None = None
    persona_name: str = "abunnytech"
    instagram_handle: str = "@abunnytech"
    tone: str = "friendly"
    sentence_length: str = "short"
    emoji_usage: str = "1-2 per reply"
    capitalization: str = "lowercase casual"
    never_say: list[str] = Field(default_factory=list)
    response_examples: dict[str, CommentResponseExample] = Field(default_factory=dict)


class CommentReplyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply_id: str
    post_url: str
    post_id: str | None = None
    run_id: str | None = None
    commenter_handle: str = ""
    comment_text: str = ""
    comment_signature: str = ""
    comment_category: CommentCategory = CommentCategory.GENERAL
    response_text: str = ""
    dm_triggered: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommentEngagementSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CommentEngagementStatus = CommentEngagementStatus.NOT_RUN
    total_replies_logged: int = 0
    replies_posted_this_run: int = 0
    last_run_at: datetime | None = None
    last_reply_at: datetime | None = None
    last_reason: str | None = None
    last_error: str | None = None
    recent_replies: list[CommentReplyRecord] = Field(default_factory=list)


class ReelSurfaceMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reel_id: str
    source_url: str
    video_download_url: str | None = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    creator_handle: str | None = None
    caption_text: str | None = None
    is_ugc_candidate: bool | None = None
    ugc_reason: str | None = None
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


class VeoPromptPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str = ""
    user_prompt: str = ""
    full_prompt: str = ""
    artifact_dir: str = ""
    system_prompt_path: str = ""
    user_prompt_path: str = ""
    full_prompt_path: str = ""


class VeoGenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect_ratio: str = "9:16"
    duration_seconds: int = Field(default=8, ge=1, le=60)


class GenerationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    template_id: str
    product_id: str
    veo_prompt: str
    product_title: str = ""
    product_description: str = ""
    creative_brief: str = ""
    prompt_package: VeoPromptPackage = Field(default_factory=VeoPromptPackage)
    generation_config: VeoGenerationConfig = Field(default_factory=VeoGenerationConfig)
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


class InstagramPostDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: str
    hashtags: list[str] = Field(default_factory=list)
    content_tier: str = ""
    funnel_position: str = ""
    product_name: str = ""
    product_tags: list[str] = Field(default_factory=list)
    brand_tags: list[str] = Field(default_factory=list)
    audio_hook_text: str = ""
    target_niche: str = ""
    thumbnail_text: str = ""
    source_blueprint_id: str = ""


class HackathonRunStatus(StrEnum):
    RUNNING = "running"
    READY = "ready"
    POSTED = "posted"
    FAILED = "failed"


class HackathonRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: HackathonRunStatus = HackathonRunStatus.RUNNING
    dry_run: bool = True
    source_db_path: str = ""
    avatar_image_path: str | None = None
    product_image_path: str | None = None
    product_title: str = ""
    product_description: str = ""
    reels_discovered: int = 0
    reels_queued: int = 0
    reels_downloaded: int = 0
    structures_persisted: int = 0
    templates_created: int = 0
    selected_template_id: str | None = None
    product_id: str | None = None
    bundle_id: str | None = None
    artifact_id: str | None = None
    video_path: str | None = None
    video_uri: str | None = None
    post_draft: InstagramPostDraft | None = None
    caption: str = ""
    post_url: str | None = None
    post_id: str | None = None
    engagement_persona: CommentEngagementPersona | None = None
    engagement_summary: CommentEngagementSummary | None = None
    error: str | None = None
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


class PostJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    platform: Literal["instagram"] = "instagram"
    media_path: str
    caption: str
    hashtags: list[str] = Field(default_factory=list)
    content_tier: str = ""
    funnel_position: str = ""
    product_name: str = ""
    product_tags: list[str] = Field(default_factory=list)
    brand_tags: list[str] = Field(default_factory=list)
    audio_hook_text: str = ""
    target_niche: str = ""
    thumbnail_text: str = ""
    source_blueprint_id: str = ""
    dry_run: bool = True


class PostedContentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_url: str
    platform: Literal["instagram"] = "instagram"
    job_id: str
    content_tier: str = ""
    funnel_position: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    product_name: str = ""
    product_tag: str | None = None
    brand_tags: list[str] = Field(default_factory=list)
    audio_hook_text: str = ""
    target_niche: str = ""
    thumbnail_text: str = ""
    source_blueprint_id: str = ""
    analytics_check_intervals: list[str] = Field(default_factory=list)
    engagement_summary: CommentEngagementSummary | None = None
    posted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PostAnalyticsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    post_id: str
    scheduled_check: str | None = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    follows_gained: int = 0
    retention_curve_pct: dict[str, int] = Field(default_factory=dict)
    retention_takeaway: str | None = None
    adaptation_recommendation: str | None = None
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
