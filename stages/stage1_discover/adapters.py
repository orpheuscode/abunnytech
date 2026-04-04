from __future__ import annotations

import random
from typing import Protocol

import structlog

from packages.contracts.base import Platform
from packages.contracts.discovery import CompetitorWatchItem, TrendingAudioItem

log = structlog.get_logger(__name__)


class TrendDiscoveryAdapter(Protocol):
    async def fetch_trending(self, platform: Platform, count: int) -> list[TrendingAudioItem]: ...


class CompetitorAnalysisAdapter(Protocol):
    async def analyze(self, platform: Platform, handle: str) -> CompetitorWatchItem: ...


_TIKTOK_SOUND_BANK: list[tuple[str, str, str, int, float, str]] = [
    (
        "snd_roman-empire-2026",
        "Roman Empire (slowed + reverb)",
        "Creator Collective",
        2_400_000,
        0.42,
        "lifestyle",
    ),
    (
        "snd_girl-dinner-v3",
        "Girl Dinner — jazz lofi chop",
        "NY Deli Beats",
        1_890_000,
        0.31,
        "food",
    ),
    (
        "snd_murder-dancefloor-sped",
        "Murder on the Dancefloor (1.25x)",
        "Sophie Ellis-Bextor",
        5_100_000,
        0.18,
        "dance",
    ),
    (
        "snd_apt-challenge",
        "APT. (sped up TikTok mix)",
        "ROSÉ & Bruno Mars",
        8_200_000,
        0.27,
        "trend",
    ),
    (
        "snd_get-ready-with-me",
        "GRWM morning routine — soft pop",
        "Studio Aurora",
        980_000,
        0.22,
        "beauty",
    ),
    (
        "snd_storytime-thumbnail",
        "Storytime tension bed (piano)",
        "Hooks Audio",
        3_450_000,
        0.35,
        "storytime",
    ),
    (
        "snd_clean-girl-aesthetic",
        "Clean girl aesthetic walk",
        "Velvet Labs",
        1_120_000,
        0.29,
        "fashion",
    ),
    (
        "snd_ai-slop-irony",
        "AI slop but make it camp",
        "Meme Foundry",
        760_000,
        0.51,
        "comedy",
    ),
    (
        "snd_duolingo-unhinged",
        "Unhinged Duolingo reminder (remix)",
        "Green Owl Sound",
        4_400_000,
        0.39,
        "comedy",
    ),
    (
        "snd_study-with-me-lofi",
        "Study with me — rain + vinyl crackle",
        "Focus Crate",
        2_050_000,
        0.14,
        "productivity",
    ),
    (
        "snd_90s-nostalgia-filter",
        "90s camcorder flash + shutter sfx",
        "Retro Kit",
        1_670_000,
        0.24,
        "nostalgia",
    ),
    (
        "snd_outfit-check-whoosh",
        "Outfit check whoosh transition",
        "SFX Pack Vol. 7",
        6_800_000,
        0.33,
        "fashion",
    ),
]


class MockTrendDiscovery:
    """Deterministic-enough mock trending feed for hackathon demos."""

    async def fetch_trending(self, platform: Platform, count: int) -> list[TrendingAudioItem]:
        log.info("mock_trend_fetch", platform=platform.value, count=count)
        pool = list(_TIKTOK_SOUND_BANK)
        random.shuffle(pool)
        picked = pool[: max(1, min(count, len(pool)))]
        return [
            TrendingAudioItem(
                platform=platform,
                audio_id=audio_id,
                title=title,
                artist=artist,
                usage_count=usage + random.randint(-50_000, 120_000),
                growth_rate=max(0.05, min(0.95, growth + random.uniform(-0.08, 0.12))),
                category=category,
                url=f"https://www.tiktok.com/music/{audio_id}" if platform == Platform.TIKTOK else "",
            )
            for audio_id, title, artist, usage, growth, category in picked
        ]


class MockCompetitorAnalysis:
    async def analyze(self, platform: Platform, handle: str) -> CompetitorWatchItem:
        log.info("mock_competitor_analyze", platform=platform.value, handle=handle)
        normalized = handle.lstrip("@").lower()
        # Deterministic pseudo-metrics from handle so repeated calls look stable.
        seed = sum(ord(c) for c in normalized) % 97
        followers = 120_000 + seed * 8_400
        engagement = 0.035 + (seed % 17) * 0.0045
        themes_pool = [
            "GRWM",
            "Storytime",
            "Productivity vlogs",
            "Small business packaging",
            "BookTok deep dives",
            "Fit checks / streetwear",
            "Skincare science",
            "AI tools for creators",
        ]
        start = seed % len(themes_pool)
        themes = [themes_pool[(start + i) % len(themes_pool)] for i in range(3)]
        posting = ["3–5 / week", "Daily", "5–7 / week", "~2 longs + 4 shorts / week"][seed % 4]
        return CompetitorWatchItem(
            platform=platform,
            account_handle=f"@{normalized}",
            account_name=f"{normalized.replace('_', ' ').title()} Official",
            follower_count=followers,
            avg_engagement_rate=round(min(0.12, engagement), 4),
            top_content_themes=themes,
            posting_frequency=posting,
            notes="Mock snapshot: hooks in first 1.2s; strong CTA in caption; uses stitched duets weekly.",
        )


# --- TODO: real platform integrations (credentials, rate limits, ToS) ---
class TikTokResearchTrendDiscoveryAdapter:
    """TODO: TikTok Research / Content API trending audio once approved."""

    async def fetch_trending(self, platform: Platform, count: int) -> list[TrendingAudioItem]:
        raise NotImplementedError("TikTok official trending API not wired yet.")


class InstagramAudioTrendDiscoveryAdapter:
    """TODO: Meta Graph API Reels audio trends where available."""

    async def fetch_trending(self, platform: Platform, count: int) -> list[TrendingAudioItem]:
        raise NotImplementedError("Instagram Reels trending audio API not wired yet.")


class YouTubeShortsTrendDiscoveryAdapter:
    """TODO: YouTube Data API v3 + Shorts shelf heuristics."""

    async def fetch_trending(self, platform: Platform, count: int) -> list[TrendingAudioItem]:
        raise NotImplementedError("YouTube Shorts trending sound pipeline not wired yet.")


class ApifyCompetitorScrapeAdapter:
    """TODO: Apify or similar actor for public profile stats."""

    async def analyze(self, platform: Platform, handle: str) -> CompetitorWatchItem:
        raise NotImplementedError("External scrape-based competitor analysis not wired yet.")
