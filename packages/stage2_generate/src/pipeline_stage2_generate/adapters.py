from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from pipeline_contracts.models import VideoBlueprint


class VideoRenderProvider(Protocol):
    def render(
        self,
        blueprint: VideoBlueprint,
        output_path: Path,
        dry_run: bool,
    ) -> Path: ...


class FixtureVideoRenderProvider:
    """
    Renders a demo clip when ffmpeg is available; otherwise writes a tiny placeholder file.
    TODO: swap for real TTS/avatar compositor behind the same interface.
    """

    def render(
        self,
        blueprint: VideoBlueprint,
        output_path: Path,
        dry_run: bool,
    ) -> Path:
        if dry_run:
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            # Color bars + silent audio — authorized demo output only
            cmd = [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=blue:s=720x1280:d={max(1, min(blueprint.duration_seconds_target, 30))}",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-shortest",
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                str(output_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return output_path

        # Placeholder bytes — not a valid playable MP4 in all players; documents mock path
        stub = (
            f"STUB_VIDEO_DEMO\nblueprint={blueprint.blueprint_id}\n"
            f"title={blueprint.title}\n"
        ).encode("utf-8")
        output_path.write_bytes(stub)
        return output_path
