"""
Redo queue generator for Stage 4.

Examines PerformanceMetricRecords and flags posts that underperformed badly
enough to warrant regeneration. The suggested_mutations dict tells the
target stage exactly what to change when re-creating the content.

Thresholds for queuing:
  - Engagement rate below `redo_eng_threshold` (default 1.5%)
  - OR hook 3s retention below `redo_hook_threshold` (default 35%)
  - OR completion rate below `redo_completion_threshold` (default 15%)
  - AND the post has not already been retried `max_retries` times
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import PerformanceMetricRecord, RedoQueueItem


@dataclass
class RedoConfig:
    redo_eng_threshold: float = 1.5       # % engagement rate — below this → redo
    redo_hook_threshold: float = 35.0     # % 3s retention — below this → hook failed
    redo_completion_threshold: float = 15.0  # % completion — below this → redo
    max_retries: int = 2                  # don't queue a post more than this many times


DEFAULT_REDO_CONFIG = RedoConfig()


def _redo_reason(record: PerformanceMetricRecord, cfg: RedoConfig) -> str | None:
    """Return the primary redo reason, or None if no redo is warranted."""
    if 0 < record.hook_retention_3s_pct < cfg.redo_hook_threshold:
        return "hook_failed"
    if 0 < record.completion_rate_pct < cfg.redo_completion_threshold:
        return "low_completion"
    if record.engagement_rate_pct < cfg.redo_eng_threshold and record.views >= 100:
        return "underperformed"
    return None


def _priority(record: PerformanceMetricRecord, reason: str) -> str:
    if reason == "hook_failed" and record.views > 5000:
        return "critical"
    if record.engagement_rate_pct < 0.5 and record.views >= 500:
        return "high"
    return "medium"


def _suggested_mutations(record: PerformanceMetricRecord, reason: str) -> dict[str, Any]:
    mutations: dict[str, Any] = {}
    if reason == "hook_failed":
        current = record.hook_style or "unknown"
        # Suggest switching to a different hook style
        alternatives = [s for s in ["question", "bold_claim", "story", "tutorial"] if s != current]
        mutations["hook_style"] = alternatives[0] if alternatives else "question"
        mutations["hook_rewrite"] = True
        mutations["target_3s_retention_pct"] = 60.0
    elif reason == "low_completion":
        mutations["reduce_duration"] = True
        mutations["add_midroll_hook"] = True
        mutations["target_completion_pct"] = 35.0
    elif reason == "underperformed":
        mutations["new_trend_angle"] = True
        mutations["try_audio_swap"] = True
        if record.schedule_slot:
            mutations["avoid_schedule_slot"] = record.schedule_slot
    if reason == "wrong_schedule" and record.schedule_slot:
        mutations["avoid_schedule_slot"] = record.schedule_slot
    if reason == "audio_mismatch" and record.audio_id:
        mutations["avoid_audio_id"] = record.audio_id
    return mutations


def _target_stage(reason: str) -> str:
    if reason in ("hook_failed", "low_completion"):
        return "stage2"
    if reason == "wrong_schedule":
        return "stage3"
    if reason == "audio_mismatch":
        return "stage1"
    return "stage2"


class RedoQueueGenerator:
    """
    Scans a list of PerformanceMetricRecords and emits RedoQueueItems.

    Usage:
        gen = RedoQueueGenerator()
        items = gen.generate(records)
    """

    def __init__(self, config: RedoConfig | None = None) -> None:
        self._config = config or DEFAULT_REDO_CONFIG

    def generate(
        self,
        records: list[PerformanceMetricRecord],
        existing_retry_counts: dict[str, int] | None = None,
        dry_run: bool = False,
    ) -> list[RedoQueueItem]:
        """
        existing_retry_counts: maps distribution_record_id → how many times already retried.
        Records at or beyond max_retries are skipped.
        """
        retries = existing_retry_counts or {}
        items: list[RedoQueueItem] = []
        for record in records:
            if retries.get(record.distribution_record_id, 0) >= self._config.max_retries:
                continue
            reason = _redo_reason(record, self._config)
            if not reason:
                continue
            items.append(
                RedoQueueItem(
                    source_distribution_record_id=record.distribution_record_id,
                    source_content_package_id=record.content_package_id,
                    source_video_blueprint_id=record.video_blueprint_id,
                    redo_reason=reason,  # type: ignore[arg-type]
                    priority=_priority(record, reason),  # type: ignore[arg-type]
                    suggested_mutations=_suggested_mutations(record, reason),
                    target_stage=_target_stage(reason),  # type: ignore[arg-type]
                    retry_count=retries.get(record.distribution_record_id, 0),
                    dry_run=dry_run,
                )
            )
        # Sort critical first
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda i: priority_order.get(i.priority, 99))
        return items
