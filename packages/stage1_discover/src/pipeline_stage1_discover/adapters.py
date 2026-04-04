from __future__ import annotations

from typing import Protocol

from pipeline_contracts.models import CompetitorWatchItem, TrendingAudioItem


class DiscoveryProvider(Protocol):
    def fetch_trending_audio(self, niche: str) -> list[TrendingAudioItem]: ...

    def fetch_competitors(self, niche: str) -> list[CompetitorWatchItem]: ...


class MockDiscoveryProvider:
    """Fixture-backed discovery — no external credentials."""

    def fetch_trending_audio(self, niche: str) -> list[TrendingAudioItem]:
        return [
            TrendingAudioItem(
                audio_id="mock_audio_upbeat_1",
                title=f"Upbeat loop — {niche}",
                platform="shorts",
                trend_score=0.82,
                bpm=120,
            ),
            TrendingAudioItem(
                audio_id="mock_audio_chill_2",
                title=f"Chill hook bed — {niche}",
                platform="tiktok",
                trend_score=0.74,
                bpm=90,
            ),
        ]

    def fetch_competitors(self, niche: str) -> list[CompetitorWatchItem]:
        return [
            CompetitorWatchItem(
                competitor_id="cmp_001",
                handle=f"@{niche}_creator_alpha",
                platform="tiktok",
                notes="Strong pattern interrupts in first 1s",
                recent_hook_pattern="POV: you just learned …",
            ),
        ]
