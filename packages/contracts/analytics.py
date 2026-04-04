"""Stage 4 - Analyze & Adapt contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from packages.contracts.base import ContractBase, Platform, utc_now


class MetricType(StrEnum):
    VIEWS = "views"
    LIKES = "likes"
    COMMENTS = "comments"
    SHARES = "shares"
    FOLLOWERS = "followers"
    WATCH_TIME = "watch_time"
    ENGAGEMENT_RATE = "engagement_rate"
    CLICK_THROUGH = "click_through"


class PerformanceMetricRecord(ContractBase):
    """A single performance data point for a distributed piece of content."""

    distribution_record_id: str
    identity_id: str
    platform: Platform
    metric_type: MetricType
    value: float = 0.0
    measured_at: datetime = Field(default_factory=utc_now)
    post_age_hours: float = 0.0


class OptimizationAction(BaseModel):
    target_stage: int
    action_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    priority: int = 1


class OptimizationDirectiveEnvelope(ContractBase):
    """A set of optimization actions derived from performance analysis."""

    identity_id: str
    analysis_window_hours: float = 24.0
    directives: list[OptimizationAction] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0


class RedoReason(StrEnum):
    LOW_ENGAGEMENT = "low_engagement"
    POOR_RETENTION = "poor_retention"
    TOPIC_SHIFT = "topic_shift"
    STYLE_UPDATE = "style_update"
    MANUAL = "manual"


class RedoQueueItem(ContractBase):
    """An item queued for re-processing in Stages 1, 2, or 3."""

    identity_id: str
    original_content_id: str = ""
    target_stage: int
    reason: RedoReason
    instructions: str = ""
    priority: int = 1
    processed: bool = False
    processed_at: datetime | None = None
