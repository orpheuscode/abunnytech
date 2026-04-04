from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TrendingAudioItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_id: str
    title: str
    platform: str
    trend_score: float = Field(ge=0.0, le=1.0)
    bpm: int | None = None
    source_label: str = Field(default="mock_provider")


class CompetitorWatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competitor_id: str
    handle: str
    platform: str
    notes: str | None = None
    recent_hook_pattern: str | None = None
