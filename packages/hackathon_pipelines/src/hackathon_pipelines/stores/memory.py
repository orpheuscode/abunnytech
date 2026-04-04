"""In-memory persistence for hackathon demos (swap for SQLite/Sheets in production)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from hackathon_pipelines.contracts import (
    PostAnalyticsSnapshot,
    ProductCandidate,
    ReelSurfaceMetrics,
    VideoStructureRecord,
    VideoTemplateRecord,
)
from hackathon_pipelines.ports import (
    AnalyticsSinkPort,
    ProductCatalogPort,
    ReelMetadataSinkPort,
    TemplateStorePort,
)


class MemoryReelSink(ReelMetadataSinkPort):
    def __init__(self) -> None:
        self.rows: list[ReelSurfaceMetrics] = []

    def persist_reel_metrics(self, metrics: list[ReelSurfaceMetrics]) -> None:
        self.rows.extend(metrics)


class MemoryTemplateStore(TemplateStorePort):
    def __init__(self) -> None:
        self._structures: dict[str, VideoStructureRecord] = {}
        self._templates: dict[str, VideoTemplateRecord] = {}

    def save_structure(self, record: VideoStructureRecord) -> None:
        self._structures[record.record_id] = record

    def save_template(self, record: VideoTemplateRecord) -> None:
        self._templates[record.template_id] = record

    def list_templates(self) -> list[VideoTemplateRecord]:
        return list(self._templates.values())

    def get_template(self, template_id: str) -> VideoTemplateRecord | None:
        return self._templates.get(template_id)

    def update_template(self, record: VideoTemplateRecord) -> None:
        record.updated_at = datetime.now(UTC)
        self._templates[record.template_id] = record


class MemoryProductCatalog(ProductCatalogPort):
    def __init__(self) -> None:
        self._by_id: dict[str, ProductCandidate] = {}

    def upsert_candidates(self, candidates: list[ProductCandidate]) -> None:
        for c in candidates:
            self._by_id[c.product_id] = c

    def top_by_score(self, *, limit: int = 5) -> list[ProductCandidate]:
        ranked = sorted(self._by_id.values(), key=lambda p: p.dropship_score, reverse=True)
        return ranked[:limit]


class MemoryAnalyticsSink(AnalyticsSinkPort):
    def __init__(self) -> None:
        self.snapshots: list[PostAnalyticsSnapshot] = []

    def persist_post_analytics(self, snapshot: PostAnalyticsSnapshot) -> None:
        self.snapshots.append(snapshot)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
