"""Gemini-shaped central coordinator across discovery, generation, social, and product pipelines."""

from __future__ import annotations

import uuid

from hackathon_pipelines.contracts import OrchestratorRunSummary, PostJob
from hackathon_pipelines.pipelines.product_discovery import ProductDiscoveryPipeline
from hackathon_pipelines.pipelines.reel_discovery import ReelDiscoveryPipeline
from hackathon_pipelines.pipelines.social_media import SocialMediaPipeline
from hackathon_pipelines.pipelines.video_generation import VideoGenerationPipeline
from hackathon_pipelines.ports import TemplateStorePort


class HackathonOrchestrator:
    """
    Coordinates the four pipelines. Callers inject concrete ports (Browser Use, TwelveLabs, Gemini, Veo).
    This class does not call Gemini for meta-orchestration by default — that logic lives in
    `GeminiVideoAgentPort` and can be extended with tool-calling in a thin wrapper if needed.
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
        run_id = f"orch_{uuid.uuid4().hex[:12]}"
        notes: list[str] = []
        top = await self._products.discover_and_rank(niche_query=niche_query, top_n=3)
        notes.append(f"products_considered={len(top)}")
        tpls = await self._reels.run_discovery_cycle()
        if not tpls or not top:
            return OrchestratorRunSummary(
                run_id=run_id,
                products_ranked=len(top),
                notes=notes + ["missing_template_or_product"],
            )
        template = tpls[0]
        product = top[0]
        bundle, artifact = await self._video.generate_for_product(
            template,
            product,
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
        )
        notes.append(f"bundle={bundle.bundle_id} artifact={artifact.artifact_id}")
        return OrchestratorRunSummary(
            run_id=run_id,
            products_ranked=len(top),
            templates_created=len(tpls),
            generations=1,
            notes=notes,
        )

    async def run_publish_and_feedback(
        self,
        *,
        media_path: str,
        caption: str,
        template_id: str,
        dry_run: bool = True,
    ) -> OrchestratorRunSummary:
        from hackathon_pipelines.stores.memory import new_id

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
