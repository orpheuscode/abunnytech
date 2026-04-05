"""In-memory persistence for hackathon demos (swap for SQLite/Sheets in production)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from hackathon_pipelines.contracts import (
    CommentEngagementSummary,
    CommentReplyRecord,
    PostAnalyticsSnapshot,
    PostedContentRecord,
    ProductCandidate,
    ReelSurfaceMetrics,
    VideoStructureRecord,
    VideoTemplateRecord,
)
from hackathon_pipelines.ports import (
    AnalyticsSinkPort,
    PostedContentSinkPort,
    ProductCatalogPort,
    ReelMetadataSinkPort,
    TemplateStorePort,
)
from hackathon_pipelines.scoring import rank_products


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
        return rank_products(self._by_id.values(), limit=limit)


class MemoryAnalyticsSink(AnalyticsSinkPort):
    def __init__(self) -> None:
        self.snapshots: list[PostAnalyticsSnapshot] = []

    def persist_post_analytics(self, snapshot: PostAnalyticsSnapshot) -> None:
        self.snapshots.append(snapshot)


class MemoryPostedContentSink(PostedContentSinkPort):
    def __init__(self) -> None:
        self.records: dict[str, PostedContentRecord] = {}
        self.comment_replies: dict[str, CommentReplyRecord] = {}

    def persist_posted_content(self, record: PostedContentRecord) -> None:
        self.records[record.post_url] = record

    def list_posted_content(self) -> list[PostedContentRecord]:
        return sorted(
            self.records.values(),
            key=lambda record: (record.posted_at, record.post_url),
            reverse=True,
        )

    def get_posted_content(self, post_url: str) -> PostedContentRecord | None:
        return self.records.get(post_url)

    def update_posted_content_engagement(
        self,
        post_url: str,
        summary: CommentEngagementSummary,
    ) -> PostedContentRecord | None:
        record = self.records.get(post_url)
        if record is None:
            return None
        updated = record.model_copy(update={"engagement_summary": summary})
        self.records[post_url] = updated
        return updated

    def persist_comment_reply(self, record: CommentReplyRecord) -> None:
        self.comment_replies[record.reply_id] = record

    def list_comment_replies(self, post_url: str | None = None) -> list[CommentReplyRecord]:
        replies = list(self.comment_replies.values())
        if post_url is not None:
            replies = [reply for reply in replies if reply.post_url == post_url]
        return sorted(
            replies,
            key=lambda reply: (reply.created_at, reply.reply_id),
            reverse=True,
        )


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
