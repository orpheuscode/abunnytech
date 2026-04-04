from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Provenance(BaseModel):
    """Where a payload or artifact originated (audit-friendly, no business rules)."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(
        ...,
        description="Logical source system or provider identifier (e.g. stage name, vendor id).",
    )
    run_id: str | None = Field(
        default=None,
        description="Pipeline run correlation id when this object was produced.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when provenance was recorded.",
    )


class Envelope(BaseModel):
    """Versioned wrapper for directive or sync payloads; inner shape is consumer-defined."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="1",
        description="Version of the inner payload contract; bump when payload keys or semantics change.",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Opaque JSON object interpreted by the target stage.",
    )
