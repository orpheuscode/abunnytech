from __future__ import annotations

import uuid

from media_pipeline.models import (
    AdaptedScript,
    AudioUnderlaySpec,
    CropSpec,
    OverlaySpec,
    PostProductionManifest,
    SubtitleTrackSpec,
)
from pipeline_contracts.models import VideoBlueprint


def build_post_production_manifest(
    blueprint: VideoBlueprint,
    script: AdaptedScript,
    *,
    raw_video_placeholder: str,
    voiceover_placeholder: str | None,
    output_video_placeholder: str,
    subtitles_path_placeholder: str,
    trending_audio_id: str | None,
) -> PostProductionManifest:
    """
    Build ffmpeg/moviepy-oriented manifest: 9:16 crop, overlays from beats,
    subtitle track, optional trending-audio underlay.
    """
    overlays: list[OverlaySpec] = []
    t = 0.0
    for seg in script.segments:
        start = t
        end = t + seg.duration_seconds
        if seg.role == "hook":
            overlays.append(
                OverlaySpec(
                    kind="text",
                    start_seconds=start,
                    end_seconds=end,
                    text=seg.text[:140],
                    position="center",
                    style_hint="bold_hook",
                )
            )
        elif seg.role == "beat":
            overlays.append(
                OverlaySpec(
                    kind="lower_third",
                    start_seconds=start,
                    end_seconds=end,
                    text=seg.text[:120],
                    position="bottom",
                )
            )
        t = end

    underlay = (
        AudioUnderlaySpec(mode="trending", trending_audio_id=trending_audio_id, mix_level_db=-14.0)
        if trending_audio_id
        else AudioUnderlaySpec(mode="silent")
    )

    return PostProductionManifest(
        manifest_id=f"ppm_{uuid.uuid4().hex[:12]}",
        blueprint_id=blueprint.blueprint_id,
        input_video_placeholder=raw_video_placeholder,
        voiceover_audio_placeholder=voiceover_placeholder,
        crop=CropSpec(target_aspect="9:16", mode="center_crop"),
        overlays=overlays,
        subtitles=SubtitleTrackSpec(
            format="srt",
            path_placeholder=subtitles_path_placeholder,
            burn_in=True,
        ),
        audio_underlay=underlay,
        output_video_placeholder=output_video_placeholder,
        notes="moviepy/ffmpeg: scale/crop to 1080x1920, overlay text, burn subtitles, duck underlay.",
    )
