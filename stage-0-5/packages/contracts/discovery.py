"""Stage 1 - Discovery & Analysis contracts."""

from datetime import datetime

from pydantic import BaseModel, Field

from packages.contracts.base import ContractBase, Platform, utc_now


class TrendingAudioItem(ContractBase):
    """A trending audio/sound discovered on a platform."""

    platform: Platform
    audio_id: str
    title: str
    artist: str = ""
    usage_count: int = 0
    growth_rate: float = 0.0
    category: str = ""
    url: str = ""
    discovered_at: datetime = Field(default_factory=utc_now)


class CompetitorWatchItem(ContractBase):
    """A competitor account or video being tracked for strategy."""

    platform: Platform
    account_handle: str
    account_name: str = ""
    follower_count: int = 0
    avg_engagement_rate: float = 0.0
    top_content_themes: list[str] = Field(default_factory=list)
    posting_frequency: str = ""
    notes: str = ""
    last_checked: datetime = Field(default_factory=utc_now)


class TrainingMaterial(BaseModel):
    source_url: str
    platform: Platform
    content_type: str = "video"
    title: str = ""
    engagement_score: float = 0.0
    tags: list[str] = Field(default_factory=list)
    local_path: str = ""
    transcript: str = ""


class TrainingMaterialsManifest(ContractBase):
    """Collection of analyzed content used to inform generation."""

    identity_id: str
    materials: list[TrainingMaterial] = Field(default_factory=list)
    analysis_summary: str = ""
    recommended_styles: list[str] = Field(default_factory=list)
    recommended_topics: list[str] = Field(default_factory=list)
