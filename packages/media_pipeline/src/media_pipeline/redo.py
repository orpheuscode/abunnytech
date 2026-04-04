from __future__ import annotations

from pipeline_contracts.models import (
    OptimizationDirectiveEnvelope,
    RedoQueueItem,
    VideoBlueprint,
)
from pipeline_contracts.models.enums import DirectiveTargetStage


def apply_redo_and_directives(
    blueprint: VideoBlueprint,
    *,
    redo_items: list[RedoQueueItem] | None = None,
    directives: list[OptimizationDirectiveEnvelope] | None = None,
) -> VideoBlueprint:
    """
    Apply Stage 4 redo queue items and stage2-targeted optimization directives.

    Payload keys (convention, not contracts):
    - ``new_hook``, ``new_title``, ``new_caption``, ``extra_hashtags``, ``replace_outline`` (list[str]),
      ``duration_seconds_target`` (int).
    Redo items match when ``blueprint_id`` equals the blueprint or is None (apply first item only).
    """
    data = blueprint.model_dump()
    redo_items = redo_items or []
    directives = directives or []

    for item in redo_items:
        if item.blueprint_id and item.blueprint_id != blueprint.blueprint_id:
            continue
        _apply_payload(data, item.payload)
        break

    for d in directives:
        if DirectiveTargetStage.STAGE2 not in d.target_stages:
            continue
        _apply_payload(data, d.envelope.payload)

    return VideoBlueprint.model_validate(data)


def _apply_payload(data: dict, payload: dict) -> None:
    if not payload:
        return
    if "new_hook" in payload and payload["new_hook"]:
        data["hook"] = str(payload["new_hook"])
    if "new_title" in payload and payload["new_title"]:
        data["title"] = str(payload["new_title"])
    if "new_caption" in payload and payload["new_caption"]:
        data["suggested_caption"] = str(payload["new_caption"])
    if "extra_hashtags" in payload and isinstance(payload["extra_hashtags"], list):
        base = list(data.get("hashtags") or [])
        base.extend(str(x) for x in payload["extra_hashtags"])
        data["hashtags"] = base
    if "replace_outline" in payload and isinstance(payload["replace_outline"], list):
        data["outline"] = [str(x) for x in payload["replace_outline"]]
    if "duration_seconds_target" in payload:
        try:
            data["duration_seconds_target"] = int(payload["duration_seconds_target"])
        except (TypeError, ValueError):
            pass
    if "audio_id" in payload:
        aid = payload["audio_id"]
        data["audio_id"] = str(aid) if aid is not None else None
