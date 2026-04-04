"""Central config loader for the orchestration layer.

Wraps ``packages.shared.config`` and adds pipeline-specific defaults,
feature-flag shortcuts, and kill-switch enforcement.  All env vars are
read through pydantic-settings (shared) or ``os.environ`` for the few
orchestrator-only knobs (KILL_SWITCH, LOG_LEVEL).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from packages.shared.config import Settings, get_settings
from packages.shared.feature_flags import is_dry_run, is_enabled

STAGE_ORDER: list[str] = [
    "stage0_identity",
    "stage1_discover",
    "stage2_generate",
    "stage3_distribute",
    "stage4_analyze",
]

DEMO_DEFAULTS: dict[str, Any] = {
    "identity_name": "Avery Bytes",
    "platform": "tiktok",
    "topic": "How AI short-form video pipelines actually work",
    "title": "AI Shorts Pipeline Demystified",
    "scene_count": 5,
    "competitor_handles": ["@trendcreator", "@viralcoach"],
}


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class PipelineConfig:
    """Resolved, immutable snapshot of pipeline configuration."""

    settings: Settings
    dry_run: bool
    kill_switch: bool
    stage5_enabled: bool
    log_level: str = "INFO"
    stage_order: list[str] = field(default_factory=lambda: list(STAGE_ORDER))
    demo_defaults: dict[str, Any] = field(default_factory=lambda: dict(DEMO_DEFAULTS))

    def assert_not_killed(self) -> None:
        if self.kill_switch:
            raise RuntimeError(
                "Kill switch is active (KILL_SWITCH=true) — pipeline halted. "
                "Unset the variable or set it to 'false' to resume."
            )

    def assert_stage_enabled(self, stage_name: str) -> None:
        if stage_name not in self.stage_order:
            raise ValueError(f"Unknown stage: {stage_name!r}. Valid: {self.stage_order}")


@lru_cache
def get_pipeline_config() -> PipelineConfig:
    """Build a ``PipelineConfig`` from the environment (cached)."""
    settings = get_settings()
    return PipelineConfig(
        settings=settings,
        dry_run=is_dry_run(),
        kill_switch=_env_bool("KILL_SWITCH"),
        stage5_enabled=is_enabled("stage5_monetize"),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
