from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipeline_contracts.models.common import Envelope
from pipeline_contracts.models.enums import DirectiveTargetStage, RedoReasonCode


class OptimizationDirectiveEnvelope(BaseModel):
    """Versioned optimization or policy feedback targeting one or more pipeline stages."""

    model_config = ConfigDict(extra="forbid")

    directive_id: str = Field(..., description="Unique directive identifier.")
    target_stages: list[DirectiveTargetStage] = Field(
        default_factory=list,
        description="Stages allowed to interpret this directive (stage1, stage2, stage3).",
    )
    envelope: Envelope = Field(
        ...,
        description="Versioned inner payload consumed by workers.",
    )
    rationale: str | None = Field(
        default=None,
        description="Human-readable reason for the directive (ops, safety, performance).",
    )


class RedoQueueItem(BaseModel):
    """Work item to re-run or patch a blueprint or package."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(..., description="Unique redo queue item identifier.")
    reason: str = Field(..., description="Free-text explanation for operators.")
    reason_code: RedoReasonCode | None = Field(
        default=None,
        description="Optional structured classification for routing and metrics.",
    )
    blueprint_id: str | None = Field(
        default=None,
        description="VideoBlueprint to regenerate when applicable.",
    )
    package_id: str | None = Field(
        default=None,
        description="ContentPackage to replace when applicable.",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Stage-specific hints; shape is not fixed by this contract.",
    )
