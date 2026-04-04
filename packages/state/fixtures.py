"""Demo fixture data for seeding a local database."""

from __future__ import annotations

from packages.state.models import (
    BrandOutreachRecord,
    CompetitorWatchItem,
    ContentGuidelines,
    ContentPackage,
    DistributionRecord,
    DMConversationRecord,
    IdentityMatrix,
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    PersonaArchetype,
    Platform,
    PlatformPresence,
    ProductCatalogItem,
    RedoQueueItem,
    TrendingAudioItem,
    VideoBlueprint,
    VoiceProfile,
)
from packages.state.registry import RepositoryRegistry


def _identity_fixtures() -> list[IdentityMatrix]:
    return [
        IdentityMatrix(
            name="TechTok Sarah",
            archetype=PersonaArchetype.EDUCATOR,
            tagline="Making tech simple, one short at a time",
            voice=VoiceProfile(voice_id="sarah-v1", style="friendly"),
            guidelines=ContentGuidelines(
                topics=["AI", "coding", "gadgets"],
                tone="casual-professional",
                max_video_duration_seconds=60,
                hashtag_strategy=["#techtok", "#learnontiktok", "#coding"],
            ),
            platforms=[
                PlatformPresence(platform=Platform.TIKTOK, handle="@techtok_sarah"),
                PlatformPresence(platform=Platform.INSTAGRAM, handle="@techtok.sarah"),
            ],
        ),
        IdentityMatrix(
            name="FitLife Mike",
            archetype=PersonaArchetype.MOTIVATOR,
            tagline="Your daily dose of fitness motivation",
            guidelines=ContentGuidelines(
                topics=["fitness", "nutrition", "mindset"],
                tone="energetic",
                max_video_duration_seconds=45,
            ),
            platforms=[
                PlatformPresence(platform=Platform.TIKTOK, handle="@fitlife_mike"),
            ],
        ),
    ]


def _trending_audio_fixtures() -> list[TrendingAudioItem]:
    return [
        TrendingAudioItem(
            platform=Platform.TIKTOK,
            audio_id="audio_001",
            title="Chill Beats Lo-fi",
            artist="LofiGirl",
            usage_count=150_000,
            trend_score=0.92,
        ),
        TrendingAudioItem(
            platform=Platform.INSTAGRAM,
            audio_id="audio_002",
            title="Hype Trap Intro",
            artist="BeatMaster",
            usage_count=87_000,
            trend_score=0.78,
        ),
    ]


def _competitor_watchlist_fixtures() -> list[CompetitorWatchItem]:
    return [
        CompetitorWatchItem(
            platform=Platform.TIKTOK,
            handle="@rival_creator",
            follower_count=250_000,
            avg_engagement=4.2,
            notes="Posts daily at 9 AM EST",
        ),
    ]


def _video_blueprint_fixtures() -> list[VideoBlueprint]:
    return [
        VideoBlueprint(
            title="5 AI Tools You Need in 2026",
            script="Hook: You won't believe tool #3...\n\nBody: ...",
            duration_seconds=45,
            format="short-form",
            status="approved",
        ),
    ]


def _content_package_fixtures() -> list[ContentPackage]:
    return [
        ContentPackage(
            video_url="https://cdn.example.com/videos/demo_001.mp4",
            thumbnail_url="https://cdn.example.com/thumbs/demo_001.jpg",
            caption="5 AI tools that changed my workflow 🤖",
            hashtags=["#ai", "#techtok", "#productivity"],
            platform=Platform.TIKTOK,
            status="ready",
        ),
    ]


def _distribution_record_fixtures() -> list[DistributionRecord]:
    return [
        DistributionRecord(
            platform=Platform.TIKTOK,
            post_url="https://tiktok.com/@techtok_sarah/video/demo",
            status="posted",
        ),
    ]


def _performance_metric_fixtures() -> list[PerformanceMetricRecord]:
    return [
        PerformanceMetricRecord(
            platform=Platform.TIKTOK,
            views=12_400,
            likes=980,
            comments=47,
            shares=210,
            watch_time_seconds=34.5,
        ),
    ]


def _optimization_directive_fixtures() -> list[OptimizationDirectiveEnvelope]:
    return [
        OptimizationDirectiveEnvelope(
            directives=[
                {"type": "increase_hook_strength", "priority": "high"},
                {"type": "shorten_intro", "target_seconds": 3},
            ],
        ),
    ]


def _redo_queue_fixtures() -> list[RedoQueueItem]:
    return [
        RedoQueueItem(reason="Low watch-time on first 3s", priority=1, status="pending"),
    ]


def _product_catalog_fixtures() -> list[ProductCatalogItem]:
    return [
        ProductCatalogItem(
            name="Creator Toolkit eBook",
            description="The ultimate guide to AI-powered content creation",
            price_cents=1999,
            url="https://store.example.com/creator-toolkit",
            active=True,
        ),
    ]


def _brand_outreach_fixtures() -> list[BrandOutreachRecord]:
    return [
        BrandOutreachRecord(
            brand_name="GadgetCo",
            contact_email="partnerships@gadgetco.example",
            status="lead",
            proposal="Product review series – 3 videos",
            deal_value_cents=250_000,
        ),
    ]


def _dm_conversation_fixtures() -> list[DMConversationRecord]:
    return [
        DMConversationRecord(
            platform=Platform.INSTAGRAM,
            contact_handle="@fan_user_42",
            messages=[
                {"role": "user", "text": "Love your videos!"},
                {"role": "assistant", "text": "Thanks so much! 🙏"},
            ],
            status="active",
        ),
    ]


ALL_FIXTURES: dict[str, list] = {
    "identity_matrix": _identity_fixtures(),
    "trending_audio": _trending_audio_fixtures(),
    "competitor_watchlist": _competitor_watchlist_fixtures(),
    "video_blueprints": _video_blueprint_fixtures(),
    "content_packages": _content_package_fixtures(),
    "distribution_records": _distribution_record_fixtures(),
    "performance_metrics": _performance_metric_fixtures(),
    "optimization_directives": _optimization_directive_fixtures(),
    "redo_queue": _redo_queue_fixtures(),
    "product_catalog": _product_catalog_fixtures(),
    "brand_outreach": _brand_outreach_fixtures(),
    "dm_conversations": _dm_conversation_fixtures(),
}


async def seed_all(registry: RepositoryRegistry) -> dict[str, int]:
    """Insert every fixture into the corresponding repository. Returns counts."""
    counts: dict[str, int] = {}
    for name, items in ALL_FIXTURES.items():
        repo = registry.get_repo(name)
        for item in items:
            await repo.create(item)
        counts[name] = len(items)
    return counts
