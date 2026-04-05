"""Stage 5 - Monetization contracts. Feature-flagged, must not block main demo."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from packages.contracts.base import ContractBase, Platform, utc_now


class ProductCatalogItem(ContractBase):
    """A product or service the AI creator can promote."""

    identity_id: str
    name: str
    description: str = ""
    image_url: str = ""
    price: float = 0.0
    currency: str = "USD"
    affiliate_url: str = ""
    category: str = ""
    active: bool = True


class OutreachStatus(StrEnum):
    IDENTIFIED = "identified"
    CONTACTED = "contacted"
    NEGOTIATING = "negotiating"
    ACTIVE = "active"
    COMPLETED = "completed"
    DECLINED = "declined"


class BrandOutreachRecord(ContractBase):
    """Tracking record for brand partnership outreach."""

    identity_id: str
    brand_name: str
    contact_info: str = ""
    platform: Platform = Platform.TIKTOK
    status: OutreachStatus = OutreachStatus.IDENTIFIED
    deal_value: float = 0.0
    notes: str = ""
    last_contact: datetime = Field(default_factory=utc_now)


class DMConversationRecord(ContractBase):
    """Record of a DM conversation (for brand outreach or engagement)."""

    identity_id: str
    platform: Platform
    counterparty_handle: str
    direction: str = "outbound"
    message_preview: str = ""
    sent_at: datetime = Field(default_factory=utc_now)
    context: str = ""
