from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class PerformanceMetricRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    metric_id: str
    distribution_record_id: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    raw: dict | None = None
