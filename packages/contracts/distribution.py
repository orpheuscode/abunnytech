"""Stage 3 - Distribution & Engagement contracts."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from packages.contracts.base import ContractBase, Platform, utc_now


class DistributionStatus(StrEnum):
    QUEUED = "queued"
    POSTING = "posting"
    POSTED = "posted"
    FAILED = "failed"
    DRY_RUN = "dry_run"


class DistributionRecord(ContractBase):
    """Record of a content package being posted to a platform."""

    content_package_id: str
    identity_id: str
    platform: Platform
    post_url: str = ""
    post_id: str = ""
    status: DistributionStatus = DistributionStatus.QUEUED
    posted_at: datetime | None = None
    scheduled_for: datetime | None = None
    error_message: str = ""
    dry_run: bool = True
    engagement_reply_count: int = 0
    last_engagement_check: datetime = Field(default_factory=utc_now)
