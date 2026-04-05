"""Ports for swapping live APIs vs dry-run mocks in hackathon pipelines."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from browser_runtime.types import AgentResult, AgentTask

from hackathon_pipelines.contracts import (
    CommentEngagementSummary,
    CommentReplyRecord,
    GeneratedVideoArtifact,
    GenerationBundle,
    InstagramPostDraft,
    PostAnalyticsSnapshot,
    PostedContentRecord,
    ProductCandidate,
    ReelSurfaceMetrics,
    TemplateDisposition,
    VideoStructureRecord,
    VideoTemplateRecord,
)


@runtime_checkable
class ReelMetadataSinkPort(Protocol):
    def persist_reel_metrics(self, metrics: list[ReelSurfaceMetrics]) -> None: ...


@runtime_checkable
class VideoUnderstandingPort(Protocol):
    async def analyze_reel_file(self, local_video_path: str, *, reel_id: str) -> VideoStructureRecord: ...


@runtime_checkable
class TemplateStorePort(Protocol):
    def save_structure(self, record: VideoStructureRecord) -> None: ...

    def save_template(self, record: VideoTemplateRecord) -> None: ...

    def list_templates(self) -> list[VideoTemplateRecord]: ...

    def get_template(self, template_id: str) -> VideoTemplateRecord | None: ...

    def update_template(self, record: VideoTemplateRecord) -> None: ...


@runtime_checkable
class GeminiVideoAgentPort(Protocol):
    async def decide_template_disposition(
        self,
        structure: VideoStructureRecord,
        *,
        peer_templates: list[VideoTemplateRecord],
    ) -> tuple[TemplateDisposition, str, str]:
        """Returns (disposition, reason, veo_prompt_draft)."""

    async def build_generation_bundle(
        self,
        template: VideoTemplateRecord,
        product: ProductCandidate,
        *,
        product_image_path: str,
        avatar_image_path: str,
    ) -> GenerationBundle: ...

    async def build_instagram_post_draft(
        self,
        template: VideoTemplateRecord,
        product: ProductCandidate,
        *,
        bundle: GenerationBundle,
        artifact: GeneratedVideoArtifact,
        structure: VideoStructureRecord | None = None,
        metrics: ReelSurfaceMetrics | None = None,
    ) -> InstagramPostDraft: ...


@runtime_checkable
class VeoGeneratorPort(Protocol):
    async def generate_ugc_video(self, bundle: GenerationBundle) -> GeneratedVideoArtifact: ...


@runtime_checkable
class ProductCatalogPort(Protocol):
    def upsert_candidates(self, candidates: list[ProductCandidate]) -> None: ...

    def top_by_score(self, *, limit: int = 5) -> list[ProductCandidate]: ...


@runtime_checkable
class AnalyticsSinkPort(Protocol):
    def persist_post_analytics(self, snapshot: PostAnalyticsSnapshot) -> None: ...


@runtime_checkable
class PostedContentSinkPort(Protocol):
    def persist_posted_content(self, record: PostedContentRecord) -> None: ...

    def list_posted_content(self) -> list[PostedContentRecord]: ...

    def get_posted_content(self, post_url: str) -> PostedContentRecord | None: ...

    def update_posted_content_engagement(
        self,
        post_url: str,
        summary: CommentEngagementSummary,
    ) -> PostedContentRecord | None: ...

    def persist_comment_reply(self, record: CommentReplyRecord) -> None: ...

    def list_comment_replies(self, post_url: str | None = None) -> list[CommentReplyRecord]: ...


@runtime_checkable
class BrowserAutomationPort(Protocol):
    """Browser Use (or mock) — open-ended agent tasks for reels, posting, and analytics scraping."""

    async def run_task(self, task: AgentTask) -> AgentResult: ...
