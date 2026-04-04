from __future__ import annotations

from pydantic import BaseModel, Field


class Stage0Body(BaseModel):
    display_name: str
    niche: str
    tone: str = "playful"
    topics: list[str] = Field(default_factory=list)
