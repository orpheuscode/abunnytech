from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pipeline_contracts.models.enums import DistributionPlatform, DistributionStatus


class DistributionRecord(BaseModel):
    """Post-Stage 2 handoff: where and when a content package was published (or attempted)."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(..., description="Unique distribution record identifier.")
    package_id: str = Field(..., description="ContentPackage.package_id that was posted.")
    platform: DistributionPlatform = Field(
        ...,
        description="Target platform for this post.",
    )
    posted_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the post went live; null if not yet posted.",
    )
    post_url: str | None = Field(
        default=None,
        description="Canonical public URL of the post when available.",
    )
    status: DistributionStatus = Field(
        default=DistributionStatus.PENDING,
        description="Lifecycle state of the distribution attempt.",
    )
