"""State / storage layer for the abunnytech AI creator pipeline.

Provides generic repository abstractions, a SQLite implementation,
and an event bus for inter-stage orchestration.
"""

from packages.state.base import Repository
from packages.state.events import EventBus, JobRegistry
from packages.state.models import (
    AvatarProfile,
    BrandOutreachRecord,
    CompetitorWatchItem,
    ContentGuidelines,
    ContentPackage,
    ContractBase,
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
from packages.state.sqlite import Database, SQLiteRepository

__all__ = [
    "Repository",
    "Database",
    "SQLiteRepository",
    "RepositoryRegistry",
    "EventBus",
    "JobRegistry",
    "ContractBase",
    "Platform",
    "PersonaArchetype",
    "VoiceProfile",
    "AvatarProfile",
    "ContentGuidelines",
    "PlatformPresence",
    "IdentityMatrix",
    "TrendingAudioItem",
    "CompetitorWatchItem",
    "VideoBlueprint",
    "ContentPackage",
    "DistributionRecord",
    "PerformanceMetricRecord",
    "OptimizationDirectiveEnvelope",
    "RedoQueueItem",
    "ProductCatalogItem",
    "BrandOutreachRecord",
    "DMConversationRecord",
]
