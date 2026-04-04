"""Central registry that exposes one typed repository per entity."""

from __future__ import annotations

from packages.state.models import (
    BrandOutreachRecord,
    CompetitorWatchItem,
    ContentPackage,
    DistributionRecord,
    DMConversationRecord,
    IdentityMatrix,
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    ProductCatalogItem,
    RedoQueueItem,
    TrendingAudioItem,
    VideoBlueprint,
)
from packages.state.sqlite import Database, SQLiteRepository

COLLECTION_MAP: dict[str, type] = {
    "identity_matrix": IdentityMatrix,
    "video_blueprints": VideoBlueprint,
    "content_packages": ContentPackage,
    "distribution_records": DistributionRecord,
    "performance_metrics": PerformanceMetricRecord,
    "optimization_directives": OptimizationDirectiveEnvelope,
    "redo_queue": RedoQueueItem,
    "product_catalog": ProductCatalogItem,
    "brand_outreach": BrandOutreachRecord,
    "dm_conversations": DMConversationRecord,
    "trending_audio": TrendingAudioItem,
    "competitor_watchlist": CompetitorWatchItem,
}


class RepositoryRegistry:
    """One-stop shop for all repositories.  Created once at app startup."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.identity_matrix = SQLiteRepository(db, "identity_matrix", IdentityMatrix)
        self.video_blueprints = SQLiteRepository(db, "video_blueprints", VideoBlueprint)
        self.content_packages = SQLiteRepository(db, "content_packages", ContentPackage)
        self.distribution_records = SQLiteRepository(db, "distribution_records", DistributionRecord)
        self.performance_metrics = SQLiteRepository(
            db, "performance_metrics", PerformanceMetricRecord
        )
        self.optimization_directives = SQLiteRepository(
            db, "optimization_directives", OptimizationDirectiveEnvelope
        )
        self.redo_queue = SQLiteRepository(db, "redo_queue", RedoQueueItem)
        self.product_catalog = SQLiteRepository(db, "product_catalog", ProductCatalogItem)
        self.brand_outreach = SQLiteRepository(db, "brand_outreach", BrandOutreachRecord)
        self.dm_conversations = SQLiteRepository(db, "dm_conversations", DMConversationRecord)
        self.trending_audio = SQLiteRepository(db, "trending_audio", TrendingAudioItem)
        self.competitor_watchlist = SQLiteRepository(db, "competitor_watchlist", CompetitorWatchItem)

    def get_repo(self, name: str) -> SQLiteRepository:  # type: ignore[type-arg]
        if not hasattr(self, name):
            raise KeyError(f"Unknown repository: {name}")
        return getattr(self, name)

    def all_repos(self) -> dict[str, SQLiteRepository]:  # type: ignore[type-arg]
        return {name: self.get_repo(name) for name in COLLECTION_MAP}
