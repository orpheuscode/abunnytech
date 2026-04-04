from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from media_pipeline.models import (
    AdaptedScript,
    ElevenLabsAudioRequest,
    NanoBananaVideoRequest,
    PostProductionManifest,
)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def write_stage2_dry_run_bundle(
    out_dir: Path,
    *,
    adapted_script: AdaptedScript,
    elevenlabs: ElevenLabsAudioRequest,
    nano_banana: NanoBananaVideoRequest,
    postprod: PostProductionManifest,
    caption_meta: dict[str, Any],
    asset_manifest: dict[str, Any],
) -> dict[str, str]:
    """
    Write adapter request JSON, postprod manifest, and placeholder asset manifest.

    Returns map of logical name -> absolute path string.
    """
    paths: dict[str, str] = {}
    p1 = out_dir / "elevenlabs_audio_request.json"
    write_json(p1, elevenlabs.model_dump(mode="json"))
    paths["elevenlabs_audio_request"] = str(p1.resolve())

    p2 = out_dir / "nano_banana_video_request.json"
    write_json(p2, nano_banana.model_dump(mode="json"))
    paths["nano_banana_video_request"] = str(p2.resolve())

    p3 = out_dir / "post_production_manifest.json"
    write_json(p3, postprod.model_dump(mode="json"))
    paths["post_production_manifest"] = str(p3.resolve())

    p4 = out_dir / "adapted_script.json"
    write_json(p4, adapted_script.model_dump(mode="json"))
    paths["adapted_script"] = str(p4.resolve())

    p5 = out_dir / "caption_metadata.json"
    write_json(p5, caption_meta)
    paths["caption_metadata"] = str(p5.resolve())

    p6 = out_dir / "placeholder_asset_manifest.json"
    write_json(p6, asset_manifest)
    paths["placeholder_asset_manifest"] = str(p6.resolve())

    return paths


def write_minimal_srt_stub(path: Path, script: AdaptedScript) -> None:
    """Minimal SRT for dry-run postprod subtitle path resolution."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["1", "00:00:00,000 --> 00:00:03,000", script.segments[0].text[:200] if script.segments else "", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
