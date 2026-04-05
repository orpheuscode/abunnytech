"""Contract-compatible models for all pipeline entities.

These mirror the shapes declared in packages/contracts and serve as the
working models for the state layer.  When the full contracts modules
(discovery, content, distribution, analytics, monetization) are published
by the contracts owner, downstream code can switch imports with no
schema change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared helpers & base
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(UTC)


class Platform(StrEnum):
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    TWITTER = "twitter"


class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=_utc_now)
    action: str
    actor: str = "system"
    details: dict[str, Any] = Field(default_factory=dict)


class ContractBase(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    audit_log: list[AuditEntry] = Field(default_factory=list)

    def add_audit(self, action: str, actor: str = "system", **details: Any) -> None:
        self.audit_log.append(AuditEntry(action=action, actor=actor, details=details))
        self.updated_at = _utc_now()


# ---------------------------------------------------------------------------
# Stage 0 – Identity
# ---------------------------------------------------------------------------

class PersonaArchetype(StrEnum):
    EDUCATOR = "educator"
    ENTERTAINER = "entertainer"
    MOTIVATOR = "motivator"
    REVIEWER = "reviewer"
    STORYTELLER = "storyteller"


class VoiceProfile(BaseModel):
    voice_id: str = ""
    provider: str = "elevenlabs"
    pitch: float = 1.0
    speed: float = 1.0
    style: str = "neutral"
    sample_url: str = ""


class AvatarProfile(BaseModel):
    avatar_url: str = ""
    style: str = "realistic"
    background_color: str = "#000000"
    overlay_template: str = ""


class ContentGuidelines(BaseModel):
    topics: list[str] = Field(default_factory=list)
    forbidden_topics: list[str] = Field(default_factory=list)
    tone: str = "casual-professional"
    max_video_duration_seconds: int = 60
    preferred_formats: list[str] = Field(default_factory=lambda: ["short-form", "tutorial"])
    hashtag_strategy: list[str] = Field(default_factory=list)
    cta_templates: list[str] = Field(default_factory=list)


class PlatformPresence(BaseModel):
    platform: Platform
    handle: str
    bio: str = ""
    active: bool = True


class IdentityMatrix(ContractBase):
    """The persona definition that feeds every stage of the pipeline."""
    name: str
    archetype: PersonaArchetype
    tagline: str = ""
    voice: VoiceProfile = Field(default_factory=VoiceProfile)
    avatar: AvatarProfile = Field(default_factory=AvatarProfile)
    guidelines: ContentGuidelines = Field(default_factory=ContentGuidelines)
    platforms: list[PlatformPresence] = Field(default_factory=list)
    ai_disclosure: str = "This content is AI-generated."


# ---------------------------------------------------------------------------
# Stage 1 – Discovery
# ---------------------------------------------------------------------------

class TrendingAudioItem(ContractBase):
    platform: Platform = Platform.TIKTOK
    audio_id: str = ""
    title: str = ""
    artist: str = ""
    usage_count: int = 0
    trend_score: float = 0.0
    discovered_at: datetime = Field(default_factory=_utc_now)


class CompetitorWatchItem(ContractBase):
    platform: Platform = Platform.TIKTOK
    handle: str = ""
    follower_count: int = 0
    avg_engagement: float = 0.0
    notes: str = ""
    tracked_since: datetime = Field(default_factory=_utc_now)


class TrainingMaterialsManifest(ContractBase):
    identity_id: UUID | None = None
    materials: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "pending"


# ---------------------------------------------------------------------------
# Stage 2 – Content
# ---------------------------------------------------------------------------

class VideoBlueprint(ContractBase):
    identity_id: UUID | None = None
    title: str = ""
    script: str = ""
    audio_id: str = ""
    duration_seconds: int = 30
    format: str = "short-form"
    status: str = "draft"


class ContentPackage(ContractBase):
    blueprint_id: UUID | None = None
    identity_id: UUID | None = None
    video_url: str = ""
    thumbnail_url: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    platform: Platform = Platform.TIKTOK
    status: str = "pending"


# ---------------------------------------------------------------------------
# Stage 3 – Distribution
# ---------------------------------------------------------------------------

class DistributionRecord(ContractBase):
    content_package_id: UUID | None = None
    platform: Platform = Platform.TIKTOK
    posted_at: datetime | None = None
    post_url: str = ""
    status: str = "pending"
    error_message: str = ""


# ---------------------------------------------------------------------------
# Stage 4 – Analytics
# ---------------------------------------------------------------------------

class PerformanceMetricRecord(ContractBase):
    distribution_id: UUID | None = None
    platform: Platform = Platform.TIKTOK
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    watch_time_seconds: float = 0.0
    collected_at: datetime = Field(default_factory=_utc_now)


class OptimizationDirectiveEnvelope(ContractBase):
    identity_id: UUID | None = None
    directives: list[dict[str, Any]] = Field(default_factory=list)
    source_metric_ids: list[UUID] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utc_now)


class RedoQueueItem(ContractBase):
    content_package_id: UUID | None = None
    reason: str = ""
    priority: int = 0
    status: str = "pending"
    requested_at: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Stage 5 – Monetization
# ---------------------------------------------------------------------------

class ProductCatalogItem(ContractBase):
    identity_id: UUID | None = None
    name: str = ""
    description: str = ""
    image_url: str = ""
    price_cents: int = 0
    url: str = ""
    affiliate_code: str = ""
    active: bool = True


class BrandOutreachRecord(ContractBase):
    identity_id: UUID | None = None
    brand_name: str = ""
    contact_email: str = ""
    status: str = "lead"
    proposal: str = ""
    deal_value_cents: int = 0


class DMConversationRecord(ContractBase):
    identity_id: UUID | None = None
    platform: Platform = Platform.TIKTOK
    contact_handle: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "active"
    last_message_at: datetime = Field(default_factory=_utc_now)
