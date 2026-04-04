from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BrandOutreachRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    outreach_id: str
    brand_name: str
    status: str = "draft"
    last_contacted_at: datetime | None = None
