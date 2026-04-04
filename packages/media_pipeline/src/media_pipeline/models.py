from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScriptSegment(BaseModel):
    """Single timed block preserving hook / beat / CTA structure from the blueprint."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["hook", "beat", "cta"] = Field(..., description="Structural role in the short.")
    text: str = Field(..., description="Narration or on-screen copy for this block.")
    duration_seconds: float = Field(..., ge=0.0, description="Target duration for this segment.")
    beat_index: int | None = Field(
        default=None,
        description="When role is beat, index into VideoBlueprint.outline.",
    )


class AdaptedScript(BaseModel):
    """Script derived from a VideoBlueprint with explicit per-segment timing."""

    model_config = ConfigDict(extra="forbid")

    blueprint_id: str
    total_duration_seconds: float = Field(..., ge=0.0)
    segments: list[ScriptSegment] = Field(default_factory=list)
    full_voiceover_text: str = Field(
        default="",
        description="Concatenated narration suitable for TTS (with light punctuation).",
    )


class ElevenLabsAudioRequest(BaseModel):
    """ElevenLabs TTS-compatible request body (adapter may map field names for API versions)."""

    model_config = ConfigDict(extra="forbid")

    voice_id: str
    text: str
    model_id: str = Field(default="eleven_multilingual_v2")
    stability: float = Field(default=0.5, ge=0.0, le=1.0)
    similarity_boost: float = Field(default=0.75, ge=0.0, le=1.0)
    style: float = Field(default=0.0, ge=0.0, le=1.0)
    use_speaker_boost: bool = True


class NanoBananaVideoRequest(BaseModel):
    """Nano Banana–style video generation request (prompt-first, reference avatar)."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    negative_prompt: str | None = None
    aspect_ratio: str = Field(default="9:16")
    duration_seconds: int = Field(default=15, ge=1, le=600)
    reference_avatar_id: str
    provider: str = Field(default="nano_banana")
    style_tags: list[str] = Field(default_factory=list)
    seed: int | None = None


class OverlaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "lower_third", "logo"] = "text"
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    text: str = ""
    position: Literal["top", "center", "bottom"] = "bottom"
    style_hint: str | None = None


class SubtitleTrackSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["srt", "ass", "vtt"] = "srt"
    path_placeholder: str = Field(
        ...,
        description="Resolved at render time to subtitles file path.",
    )
    burn_in: bool = Field(default=True, description="If true, bake subtitles into output video.")


class CropSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_aspect: Literal["9:16", "1:1", "16:9"] = "9:16"
    mode: Literal["center_crop", "scale_pad"] = "center_crop"


class AudioUnderlaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["trending", "silent"] = "silent"
    trending_audio_id: str | None = None
    mix_level_db: float = Field(
        default=-12.0,
        description="Relative level for underlay vs main voiceover (negative = quieter bed).",
    )


class PostProductionManifest(BaseModel):
    """Operations manifest for ffmpeg or moviepy post-production."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str
    blueprint_id: str
    input_video_placeholder: str = Field(
        ...,
        description="Path or URI placeholder for raw generated video before post.",
    )
    voiceover_audio_placeholder: str | None = Field(
        default=None,
        description="Optional separate narration track from ElevenLabs output.",
    )
    crop: CropSpec = Field(default_factory=CropSpec)
    overlays: list[OverlaySpec] = Field(default_factory=list)
    subtitles: SubtitleTrackSpec | None = None
    audio_underlay: AudioUnderlaySpec = Field(default_factory=AudioUnderlaySpec)
    output_video_placeholder: str = Field(
        ...,
        description="Final primary deliverable path after compositing.",
    )
    notes: str | None = Field(default=None, description="Human notes for operators or moviepy scripts.")
