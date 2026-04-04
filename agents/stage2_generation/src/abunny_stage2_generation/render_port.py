from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pipeline_contracts.models import VideoBlueprint


class VideoRenderPort(Protocol):
    """Same contract as ``VideoRenderProvider`` in pipeline_stage2_generate (structural match)."""

    def render(
        self,
        blueprint: VideoBlueprint,
        output_path: Path,
        dry_run: bool,
    ) -> Path: ...
