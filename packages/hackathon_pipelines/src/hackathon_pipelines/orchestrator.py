"""Gemini-shaped central coordinator across discovery, generation, social, and product pipelines."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from hackathon_pipelines.contracts import (
    ClosedLoopRunSummary,
    GeneratedVideoArtifact,
    GenerationBundle,
    OrchestratorRunSummary,
    PostJob,
    ProductCandidate,
    VideoTemplateRecord,
)
from hackathon_pipelines.pipelines.product_discovery import ProductDiscoveryPipeline
from hackathon_pipelines.pipelines.reel_discovery import ReelDiscoveryPipeline
from hackathon_pipelines.pipelines.social_media import SocialMediaPipeline
from hackathon_pipelines.pipelines.video_generation import VideoGenerationPipeline
from hackathon_pipelines.ports import TemplateStorePort


class HackathonOrchestrator:
    """
    Coordinates the four pipelines. Callers inject concrete ports (Browser Use, TwelveLabs, Gemini, Veo).
    For Gemini-driven sequencing of these methods via function calling, use
    `hackathon_pipelines.gemini_tool_orchestrator.run_gemini_pipeline_orchestration`.
    """

    def __init__(
        self,
        *,
        reel_discovery: ReelDiscoveryPipeline,
        video_generation: VideoGenerationPipeline,
        social: SocialMediaPipeline,
        products: ProductDiscoveryPipeline,
        templates: TemplateStorePort,
    ) -> None:
        self._reels = reel_discovery
        self._video = video_generation
        self._social = social
        self._products = products
        self._templates = templates

    def _latest_template(self) -> VideoTemplateRecord | None:
        templates = self._templates.list_templates()
        if not templates:
            return None
        return max(
            templates,
            key=lambda record: (
                record.updated_at or record.created_at or datetime.min.replace(tzinfo=UTC),
                record.created_at,
                record.template_id,
            ),
        )

    def _ensure_media_path(
        self,
        *,
        artifact: GeneratedVideoArtifact,
        explicit_media_path: str | None,
        dry_run: bool,
    ) -> str:
        if artifact.video_path:
            return artifact.video_path
        if explicit_media_path:
            path = Path(explicit_media_path)
        else:
            path = Path("output") / "hackathon_videos" / f"{artifact.artifact_id}.mp4"
        if dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(b"")
        return str(path)

    async def _generate_top_product_video(
        self,
        *,
        product_image_path: str,
        avatar_image_path: str,
        niche_query: str,
    ) -> tuple[
        OrchestratorRunSummary,
        VideoTemplateRecord | None,
        ProductCandidate | None,
        GenerationBundle | None,
        GeneratedVideoArtifact | None,
    ]:
        run_id = f"orch_{uuid.uuid4().hex[:12]}"
        notes: list[str] = []
        top = await self._products.discover_and_rank(niche_query=niche_query, top_n=3)
        notes.append(f"products_considered={len(top)}")
        template = self._latest_template()
        if template is None:
            templates = await self._reels.run_discovery_cycle()
            notes.append(f"templates_bootstrapped={len(templates)}")
            template = self._latest_template()
        if template is None or not top:
            return (
                OrchestratorRunSummary(
                    run_id=run_id,
                    products_ranked=len(top),
                    notes=notes + ["missing_template_or_product"],
                ),
                template,
                top[0] if top else None,
                None,
                None,
            )

        product = top[0]
        bundle, artifact = await self._video.generate_for_product(
            template,
            product,
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
        )
        notes.extend(
            [
                f"template_id={template.template_id}",
                f"product_id={product.product_id}",
                f"bundle={bundle.bundle_id}",
                f"artifact={artifact.artifact_id}",
            ]
        )
        return (
            OrchestratorRunSummary(
                run_id=run_id,
                products_ranked=len(top),
                templates_created=len(self._templates.list_templates()),
                generations=1,
                notes=notes,
            ),
            template,
            product,
            bundle,
            artifact,
        )

    async def run_reel_to_template_cycle(self) -> OrchestratorRunSummary:
        run_id = f"orch_{uuid.uuid4().hex[:12]}"
        notes: list[str] = []
        templates = await self._reels.run_discovery_cycle()
        notes.append(f"templates_created={len(templates)}")
        return OrchestratorRunSummary(
            run_id=run_id,
            reels_scanned=1,
            reels_downloaded=len(templates),
            structures_persisted=len(templates),
            templates_created=len(templates),
            notes=notes,
        )

    async def run_product_to_video(
        self,
        *,
        product_image_path: str,
        avatar_image_path: str,
        niche_query: str = "dropship",
    ) -> OrchestratorRunSummary:
        summary, _, _, _, _ = await self._generate_top_product_video(
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
            niche_query=niche_query,
        )
        return summary

    async def run_publish_and_feedback(
        self,
        *,
        media_path: str,
        caption: str,
        template_id: str,
        dry_run: bool = True,
    ) -> OrchestratorRunSummary:
        from hackathon_pipelines.stores import new_id

        run_id = f"orch_{uuid.uuid4().hex[:12]}"
        job = PostJob(job_id=new_id("post"), media_path=media_path, caption=caption, dry_run=dry_run)
        pub = await self._social.publish_reel(job)
        notes = [f"publish_success={pub.success}"]
        post_id = str(pub.output.get("post_id") or pub.output.get("post_url") or "unknown_post")
        tpl = self._templates.get_template(template_id)
        if tpl:
            snap = await self._social.fetch_post_analytics(post_id, dry_run=dry_run)
            updated = self._social.apply_performance_to_template(tpl, snap)
            notes.append(f"performance={updated.performance_label}")
        return OrchestratorRunSummary(run_id=run_id, posts=1, analytics_snapshots=1, notes=notes)

    async def run_closed_loop_cycle(
        self,
        *,
        product_image_path: str,
        avatar_image_path: str,
        niche_query: str = "dropship",
        caption: str = "Auto-generated UGC",
        media_path: str | None = None,
        dry_run: bool = True,
    ) -> ClosedLoopRunSummary:
        run_id = f"orch_{uuid.uuid4().hex[:12]}"
        reel_summary = await self.run_reel_to_template_cycle()
        product_summary, template, product, bundle, artifact = await self._generate_top_product_video(
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
            niche_query=niche_query,
        )
        notes = [*reel_summary.notes, *product_summary.notes]
        if template is None or artifact is None:
            notes.append("publish_skipped_missing_generation_context")
            return ClosedLoopRunSummary(
                run_id=run_id,
                reel_summary=reel_summary,
                product_summary=product_summary,
                publish_summary=None,
                template_id=template.template_id if template else None,
                product_id=product.product_id if product else None,
                bundle_id=bundle.bundle_id if bundle else None,
                artifact_id=artifact.artifact_id if artifact else None,
                media_path=media_path,
                notes=notes,
            )

        resolved_media_path = self._ensure_media_path(
            artifact=artifact,
            explicit_media_path=media_path,
            dry_run=dry_run,
        )
        publish_summary = await self.run_publish_and_feedback(
            media_path=resolved_media_path,
            caption=caption,
            template_id=template.template_id,
            dry_run=dry_run,
        )
        notes.extend(publish_summary.notes)
        return ClosedLoopRunSummary(
            run_id=run_id,
            reel_summary=reel_summary,
            product_summary=product_summary,
            publish_summary=publish_summary,
            template_id=template.template_id,
            product_id=product.product_id if product else None,
            bundle_id=bundle.bundle_id if bundle else None,
            artifact_id=artifact.artifact_id,
            media_path=resolved_media_path,
            notes=notes,
        )
