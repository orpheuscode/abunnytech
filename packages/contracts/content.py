"""Stage 2 - Content Generation contracts."""

from enum import StrEnum

from pydantic import BaseModel, Field

from packages.contracts.base import ContractBase, Platform


class ContentStatus(StrEnum):
    DRAFT = "draft"
    RENDERING = "rendering"
    RENDERED = "rendered"
    APPROVED = "approved"
    FAILED = "failed"


class SceneBlock(BaseModel):
    """A single scene/segment in a video blueprint."""

    order: int
    duration_seconds: float = 3.0
    narration_text: str = ""
    visual_prompt: str = ""
    text_overlay: str = ""
    transition: str = "cut"


class VideoBlueprint(ContractBase):
    """A scripted plan for a single video, ready for rendering."""

    identity_id: str
    title: str
    hook: str = ""
    scenes: list[SceneBlock] = Field(default_factory=list)
    target_platform: Platform = Platform.TIKTOK
    target_duration_seconds: int = 30
    audio_id: str = ""
    hashtags: list[str] = Field(default_factory=list)
    cta: str = ""
    status: ContentStatus = ContentStatus.DRAFT


class RenderedAsset(BaseModel):
    asset_type: str = "video"
    file_path: str = ""
    file_url: str = ""
    format: str = "mp4"
    resolution: str = "1080x1920"
    duration_seconds: float = 0.0
    file_size_bytes: int = 0


class ContentPackage(ContractBase):
    """A fully rendered content package ready for distribution."""

    identity_id: str
    blueprint_id: str
    title: str
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    target_platform: Platform = Platform.TIKTOK
    assets: list[RenderedAsset] = Field(default_factory=list)
    status: ContentStatus = ContentStatus.RENDERED
    ai_disclosure: str = "This content is AI-generated."
