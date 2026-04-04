"""
Stage 3 contract stubs — local definitions pending packages/contracts.

These mirror the canonical contract names from the system design:
  - IdentityMatrix     (produced by Stage 0, consumed by all stages)
  - ContentPackage     (produced by Stage 2, consumed by Stage 3)
  - DistributionRecord (produced by Stage 3, consumed by Stage 4)
  - DMConversationRecord (produced by Stage 3, consumed by Stage 4)

When packages/contracts is created, these should be replaced with imports
from that package. See docs/proposed-contract-changes/m2t2.md for the
proposed canonical schemas.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Shared enumerations (subset — contracts owner should own the canonical set)
# ---------------------------------------------------------------------------


class Platform(StrEnum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


class CommentCategory(StrEnum):
    ENGAGING = "engaging"
    QUESTION = "question"
    PRAISE = "praise"
    COMPLAINT = "complaint"
    SPAMMY = "spammy"
    TRIGGER_DM = "trigger_dm"


class DMState(StrEnum):
    IDLE = "idle"
    TRIGGER_DETECTED = "trigger_detected"
    FOLLOWER_CHECK = "follower_check"
    REPLY_PLANNED = "reply_planned"
    DM_PLANNED = "dm_planned"
    SENT = "sent"
    CONVERTED = "converted"
    REJECTED = "rejected"


class DistributionStatus(StrEnum):
    QUEUED = "queued"
    EXECUTING = "executing"
    POSTED = "posted"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


# ---------------------------------------------------------------------------
# IdentityMatrix  (Stage 0 → all stages)
# ---------------------------------------------------------------------------


class CommentStyle(BaseModel):
    """Defines how the persona responds to comments."""

    tone: str = "friendly"
    use_emojis: bool = True
    avg_reply_length: int = 80  # characters
    trigger_keywords: list[str] = Field(
        default_factory=lambda: ["link", "how", "where", "price", "buy", "shop"]
    )
    dm_offer_template: str = "Hey! DM me and I'll send you the link 🐰"
    positive_reply_templates: list[str] = Field(
        default_factory=lambda: [
            "Thank you so much! 🥰",
            "This means everything to me! 💕",
            "You made my day! 🐰✨",
        ]
    )
    question_reply_templates: list[str] = Field(
        default_factory=lambda: [
            "Great question! {answer}",
            "Omg yes! {answer} 🐰",
        ]
    )
    faq: dict[str, str] = Field(default_factory=dict)


class IdentityMatrix(BaseModel):
    """
    Core persona definition — the single source of truth for who the creator is.
    Produced by Stage 0, consumed by all downstream stages.
    """

    identity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    persona_name: str
    display_name: str
    niche: str
    bio: str = ""
    visual_style: str = ""
    voice_tags: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    target_platforms: list[Platform] = Field(default_factory=list)
    comment_style: CommentStyle = Field(default_factory=CommentStyle)
    ai_disclosure_footer: str = "✨ AI-assisted content | @{persona_name}"
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ContentPackage  (Stage 2 → Stage 3)
# ---------------------------------------------------------------------------


class ContentPackage(BaseModel):
    """
    A fully-produced content unit ready for distribution.
    Produced by Stage 2, consumed by Stage 3.
    """

    package_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    blueprint_id: str | None = None
    content_type: Literal["short_video", "story", "reel", "post", "carousel"]
    title: str
    caption: str
    hashtags: list[str] = Field(default_factory=list)
    media_path: str | None = None   # local filesystem path to the video/image
    media_url: str | None = None    # remote URL (alternative)
    thumbnail_path: str | None = None
    duration_seconds: float | None = None
    target_platforms: list[Platform] = Field(default_factory=list)
    priority: int = 5               # 1 = highest priority; used by scheduler
    identity_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# StoryEngagementPlan  (Stage 3 internal → DistributionRecord)
# ---------------------------------------------------------------------------


class StorySlide(BaseModel):
    slide_index: int
    content_type: Literal["image", "video", "text_overlay", "poll", "link_sticker"]
    caption: str = ""
    cta: str | None = None
    media_path: str | None = None
    poll_question: str | None = None
    poll_options: list[str] = Field(default_factory=list)


class StoryEngagementPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    package_id: str
    platform: Platform
    slides: list[StorySlide] = Field(default_factory=list)
    scheduled_at: datetime | None = None
    dry_run: bool = True


# ---------------------------------------------------------------------------
# DistributionRecord  (Stage 3 → Stage 4)
# ---------------------------------------------------------------------------


class DistributionRecord(BaseModel):
    """
    Emitted once per successful (or attempted) platform post.
    Consumed by Stage 4 for analytics correlation.
    """

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    package_id: str
    identity_id: str | None = None
    platform: Platform
    post_id: str | None = None         # platform-assigned post ID
    post_url: str | None = None
    status: DistributionStatus = DistributionStatus.QUEUED
    caption_used: str = ""
    hashtags_used: list[str] = Field(default_factory=list)
    posted_at: datetime | None = None
    error: str | None = None
    dry_run: bool = True
    story_plan: StoryEngagementPlan | None = None
    provider_used: str = "mock"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# DMConversationRecord  (Stage 3 → Stage 4)
# ---------------------------------------------------------------------------


class ConversionEvent(BaseModel):
    event_type: Literal["link_clicked", "product_viewed", "purchase", "follow", "dm_reply"]
    occurred_at: datetime = Field(default_factory=_utcnow)
    value_usd: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DMConversationRecord(BaseModel):
    """
    Tracks the lifecycle of a comment-triggered DM conversation.
    Consumed by Stage 4 for engagement and conversion attribution.
    """

    conv_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform
    post_id: str
    comment_id: str
    user_id: str
    comment_text: str
    comment_category: CommentCategory
    trigger_keyword: str | None = None
    fsm_state: DMState = DMState.IDLE
    reply_text: str | None = None      # public comment reply
    dm_text: str | None = None         # DM message sent
    reply_id: str | None = None        # platform reply ID
    dm_message_id: str | None = None
    conversion_events: list[ConversionEvent] = Field(default_factory=list)
    is_follower: bool | None = None    # result of follower-state check
    dry_run: bool = True
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# TriagedComment  (Stage 3 internal)
# ---------------------------------------------------------------------------


class TriagedComment(BaseModel):
    """Result of CommentTriageEngine.triage()."""

    comment_id: str
    platform: Platform
    post_id: str
    user_id: str
    text: str
    category: CommentCategory
    sentiment_score: float = 0.0   # -1.0 (negative) to 1.0 (positive)
    reply_priority: int = 5        # 1 = reply immediately
    detected_trigger: str | None = None
    triaged_at: datetime = Field(default_factory=_utcnow)
