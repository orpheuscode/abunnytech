from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from pipeline_contracts.models.enums import PlatformTarget, TrainingMaterialKind


class VoicePackRef(BaseModel):
    """Reference to a synthesized or licensed voice asset."""

    model_config = ConfigDict(extra="forbid")

    voice_id: str = Field(..., description="Stable id within the voice provider.")
    provider: str = Field(
        default="mock",
        description="Voice synthesis or library provider key.",
    )
    sample_url: HttpUrl | None = Field(
        default=None,
        description="Optional preview URL for review tooling.",
    )


class AvatarPackRef(BaseModel):
    """Reference to an avatar or visual identity pack."""

    model_config = ConfigDict(extra="forbid")

    avatar_id: str = Field(..., description="Stable id within the avatar provider.")
    provider: str = Field(
        default="mock",
        description="Avatar or render provider key.",
    )
    preview_url: HttpUrl | None = Field(
        default=None,
        description="Optional still or thumbnail URL.",
    )


class PersonaAxis(BaseModel):
    """Narrative and safety constraints for generated content."""

    model_config = ConfigDict(extra="forbid")

    tone: str = Field(
        ...,
        description="Primary voice (e.g. playful, educational, deadpan).",
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Themes the persona should lean into.",
    )
    avoid_topics: list[str] = Field(
        default_factory=list,
        description="Themes to avoid for policy or brand fit.",
    )
    disclosure_line: str | None = Field(
        default=None,
        description="Optional fixed disclosure line for regulated or demo contexts.",
    )


class IdentityMatrix(BaseModel):
    """Stage 0 output: canonical persona, voice, and platform targets for a creator lane."""

    model_config = ConfigDict(extra="forbid")

    matrix_id: str = Field(..., description="Unique identity matrix identifier.")
    display_name: str = Field(..., description="Human-facing creator or lane name.")
    niche: str = Field(..., description="Audience or vertical label.")
    persona: PersonaAxis = Field(..., description="Tone, topics, and disclosure constraints.")
    avatar: AvatarPackRef = Field(..., description="Visual identity reference.")
    voice: VoicePackRef = Field(..., description="Audio identity reference.")
    platform_targets: list[PlatformTarget] = Field(
        default_factory=lambda: [PlatformTarget.TIKTOK, PlatformTarget.SHORTS],
        description="Platforms this matrix is intended to publish on.",
    )


class TrainingMaterialItem(BaseModel):
    """Single training asset linked to an identity matrix."""

    model_config = ConfigDict(extra="forbid")

    uri: str = Field(..., description="Storage URI or path to the asset.")
    kind: TrainingMaterialKind = Field(
        ...,
        description="Asset kind (image, transcript, style_ref, document, other).",
    )
    label: str | None = Field(default=None, description="Optional human-readable label.")


class TrainingMaterialsManifest(BaseModel):
    """Optional bundle of reference materials for fine-tuning or prompting."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str = Field(..., description="Unique manifest identifier.")
    matrix_id: str = Field(..., description="Identity matrix this manifest belongs to.")
    items: list[TrainingMaterialItem] = Field(
        default_factory=list,
        description="Ordered or unordered list of training assets.",
    )
