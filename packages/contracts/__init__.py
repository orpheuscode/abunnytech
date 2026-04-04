"""Canonical Pydantic v2 contracts for the abunnytech AI creator pipeline.

These contracts define the system boundaries between all stages.
Treat this package as read-only unless you are the contracts owner.
"""

from packages.contracts.analytics import (
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    RedoQueueItem,
)
from packages.contracts.content import ContentPackage, VideoBlueprint
from packages.contracts.discovery import (
    CompetitorWatchItem,
    TrainingMaterialsManifest,
    TrendingAudioItem,
)
from packages.contracts.distribution import DistributionRecord
from packages.contracts.identity import IdentityMatrix
from packages.contracts.monetization import (
    BrandOutreachRecord,
    DMConversationRecord,
    ProductCatalogItem,
)

__all__ = [
    "IdentityMatrix",
    "TrainingMaterialsManifest",
    "VideoBlueprint",
    "TrendingAudioItem",
    "CompetitorWatchItem",
    "ContentPackage",
    "DistributionRecord",
    "PerformanceMetricRecord",
    "OptimizationDirectiveEnvelope",
    "RedoQueueItem",
    "ProductCatalogItem",
    "BrandOutreachRecord",
    "DMConversationRecord",
]
