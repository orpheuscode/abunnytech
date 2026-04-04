"""Stage 0 - Identity Matrix contract. Feeds all downstream stages."""

from enum import StrEnum

from pydantic import BaseModel, Field

from packages.contracts.base import ContractBase, Platform


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
