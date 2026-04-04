from __future__ import annotations

from pathlib import Path
from typing import Protocol

from media_pipeline.models import AdaptedScript, NanoBananaVideoRequest
from pipeline_contracts.models import IdentityMatrix, VideoBlueprint


def build_nano_banana_request(
    blueprint: VideoBlueprint,
    identity: IdentityMatrix,
    script: AdaptedScript,
) -> NanoBananaVideoRequest:
    """Compose a Nano Banana–compatible generation request from blueprint + identity + script."""
    beat_hints = " | ".join(s.text for s in script.segments if s.role == "beat")
    prompt = (
        f"{blueprint.title}. {blueprint.hook} "
        f"Vertical {script.total_duration_seconds:.0f}s short. Beats: {beat_hints}. "
        f"Tone: {identity.persona.tone}."
    ).strip()
    neg = ", ".join(identity.persona.avoid_topics) if identity.persona.avoid_topics else None
    return NanoBananaVideoRequest(
        prompt=prompt[:8000],
        negative_prompt=neg,
        aspect_ratio="9:16",
        duration_seconds=int(blueprint.duration_seconds_target),
        reference_avatar_id=identity.avatar.avatar_id,
        style_tags=list(identity.persona.topics)[:8],
    )


class NanoBananaVideoAdapter(Protocol):
    """Pluggable video generation: real Nano Banana client implements this."""

    def generate_to_path(
        self,
        request: NanoBananaVideoRequest,
        output_path: Path,
        *,
        dry_run: bool,
    ) -> Path: ...


class MockNanoBananaAdapter:
    """Placeholder raw video path for post-production; no network."""

    def generate_to_path(
        self,
        request: NanoBananaVideoRequest,
        output_path: Path,
        *,
        dry_run: bool,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if dry_run:
            output_path.write_text(
                f"DRY_RUN_VIDEO\navatar={request.reference_avatar_id}\n"
                f"dur={request.duration_seconds}\n",
                encoding="utf-8",
            )
            return output_path
        stub = (
            f"MOCK_RAW_VIDEO\nprompt_chars={len(request.prompt)}\n"
            f"avatar={request.reference_avatar_id}\n"
        ).encode()
        output_path.write_bytes(stub)
        return output_path
