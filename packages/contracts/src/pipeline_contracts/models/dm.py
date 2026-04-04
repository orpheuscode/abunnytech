from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class DMConversationRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    conversation_id: str
    platform: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: str | None = None
