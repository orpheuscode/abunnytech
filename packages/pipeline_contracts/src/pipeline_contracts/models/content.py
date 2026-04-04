from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VideoBlueprint(BaseModel):
    """Stage 1 output: creative brief and structure before generation."""

    model_config = ConfigDict(extra="forbid")

    blueprint_id: str = Field(..., description="Unique blueprint identifier.")
    matrix_id: str = Field(..., description="Identity matrix this blueprint belongs to.")
    title: str = Field(..., description="Working title for the short.")
    hook: str = Field(..., description="Opening hook or first-line concept.")
    outline: list[str] = Field(
        default_factory=list,
        description="Ordered beat list or scene prompts.",
    )
    suggested_caption: str = Field(
        default="",
        description="Draft caption before final packaging.",
    )
    hashtags: list[str] = Field(
        default_factory=list,
        description="Suggested hashtags (without leading # optional per platform).",
    )
    audio_id: str | None = Field(
        default=None,
        description="TrendingAudioItem.audio_id when a specific track is selected.",
    )
    duration_seconds_target: int = Field(
        default=15,
        ge=1,
        le=600,
        description="Target video length in seconds.",
    )


class MediaAssetRef(BaseModel):
    """Pointer to a rendered binary (path, object store key, or local dev path)."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="Filesystem path, object key, or URI string.")
    mime_type: str = Field(
        default="video/mp4",
        description="IANA media type for the primary asset.",
    )
    bytes_approx: int | None = Field(
        default=None,
        ge=0,
        description="Approximate size in bytes for quota checks.",
    )


class ContentPackage(BaseModel):
    """Stage 2 output: publishable bundle tied to a blueprint and run."""

    model_config = ConfigDict(extra="forbid")

    package_id: str = Field(..., description="Unique content package identifier.")
    run_id: str = Field(..., description="Pipeline run that produced this package.")
    blueprint_id: str = Field(..., description="Source VideoBlueprint id.")
    matrix_id: str = Field(..., description="Identity matrix for disclosure and voice/avatar context.")
    primary_video: MediaAssetRef = Field(..., description="Main deliverable video asset.")
    caption: str = Field(..., description="Final caption text for posting.")
    hashtags: list[str] = Field(
        default_factory=list,
        description="Hashtags to include at post time.",
    )
    disclosure_tag: str | None = Field(
        default="#AIcreatorDemo",
        description="Visible disclosure hashtag or tag for sandbox or regulated posts.",
    )
