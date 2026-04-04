"""Stage-local models for scoring, drafts, attribution, and approval.

These extend the canonical contracts in packages/contracts/monetization.py
without modifying that shared package.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from packages.contracts.base import ContractBase, Platform, utc_now

# ---------------------------------------------------------------------------
# Product scoring
# ---------------------------------------------------------------------------

class ProductScore(ContractBase):
    """Score assigned to a ProductCatalogItem by the scoring pipeline."""

    product_id: str
    identity_id: str
    relevance_score: float = Field(0.0, ge=0.0, le=1.0)
    audience_fit_score: float = Field(0.0, ge=0.0, le=1.0)
    margin_score: float = Field(0.0, ge=0.0, le=1.0)
    composite_score: float = Field(0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    scored_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Listing / Shopify drafts
# ---------------------------------------------------------------------------

class ListingDraftStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class ListingDraft(ContractBase):
    """A store-listing draft (e.g. Shopify) produced in dry-run mode."""

    product_id: str
    identity_id: str
    platform: str = "shopify"
    title: str = ""
    body_html: str = ""
    price: float = 0.0
    currency: str = "USD"
    tags: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    status: ListingDraftStatus = ListingDraftStatus.DRAFT
    external_listing_id: str = ""
    dry_run: bool = True
    approved_by: str = ""
    approved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Outreach drafts
# ---------------------------------------------------------------------------

class OutreachDraft(ContractBase):
    """A generated outreach message draft for brand partnerships."""

    outreach_record_id: str
    identity_id: str
    brand_name: str
    platform: Platform = Platform.TIKTOK
    subject: str = ""
    body: str = ""
    tone: str = "professional"
    call_to_action: str = ""
    status: ListingDraftStatus = ListingDraftStatus.DRAFT
    dry_run: bool = True
    approved_by: str = ""
    approved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

class AttributionSource(StrEnum):
    DISTRIBUTION = "distribution"
    ENGAGEMENT = "engagement"
    DM_CONVERSATION = "dm_conversation"
    ORGANIC = "organic"


class AttributionRecord(ContractBase):
    """Links a monetization event back to Stage 3/4 distribution and analytics."""

    identity_id: str
    product_id: str = ""
    outreach_record_id: str = ""
    distribution_record_id: str = ""
    source: AttributionSource = AttributionSource.ORGANIC
    platform: Platform = Platform.TIKTOK
    estimated_revenue: float = 0.0
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    attribution_window_hours: float = 72.0
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)
    computed_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------

class ApprovalAction(StrEnum):
    PUBLISH_LISTING = "publish_listing"
    SEND_OUTREACH = "send_outreach"
    SEND_DM = "send_dm"
    PURCHASE = "purchase"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequest(ContractBase):
    """Manual approval gate for any purchase- or send-related action."""

    identity_id: str
    action: ApprovalAction
    target_id: str
    description: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer: str = ""
    reviewed_at: datetime | None = None
    review_notes: str = ""
    auto_expire_hours: float = 48.0
    context: dict[str, Any] = Field(default_factory=dict)
