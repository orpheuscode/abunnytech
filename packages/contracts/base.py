"""Base types shared across all contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> UUID:
    return uuid4()


class Platform(StrEnum):
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    TWITTER = "twitter"


class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    action: str
    actor: str = "system"
    details: dict[str, Any] = Field(default_factory=dict)


class ContractBase(BaseModel):
    """All contracts extend this to get id, timestamps, and audit trail."""

    id: UUID = Field(default_factory=new_id)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    audit_log: list[AuditEntry] = Field(default_factory=list)

    def add_audit(self, action: str, actor: str = "system", **details: Any) -> None:
        self.audit_log.append(
            AuditEntry(action=action, actor=actor, details=details)
        )
        self.updated_at = utc_now()
