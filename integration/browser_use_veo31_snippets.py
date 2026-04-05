"""Integration snippets for Browser Use + Gemini + Veo 3.1.

These snippets are intentionally separate from the main runtime path so the
team can drop in live Browser Use session handling and asset upload helpers
without destabilizing the currently passing dry-run pipeline.

Primary use cases:
1. Reel discovery pipeline via Browser Use
2. Product discovery pipeline via Browser Use
3. Social media publish + analytics loop
4. Direct Veo 3.1 generation from avatar image + prompt + product image
5. Full closed-loop storefront pipeline
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from browser_runtime.providers.browser_use import BrowserUseBrowserConfig, BrowserUseProvider
from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, TwelveLabsUnderstanding
from hackathon_pipelines.contracts import (
    GeneratedVideoArtifact,
    GenerationBundle,
    VeoGenerationConfig,
)
from hackathon_pipelines.ports import VeoGeneratorPort
from hackathon_pipelines.prototype_bridge import build_veo_prompt_package
from hackathon_pipelines.video_io import (
    build_output_video_path,
    download_video_to_path,
    render_demo_bundle_video,
)

from hackathon_pipelines import build_runtime_stack


class ReferenceImageUploader(Protocol):
    """Team-owned upload seam for Vertex AI reference-image inputs."""

    def __call__(self, local_path: str) -> tuple[str, str]:
        """Return ``(gcs_uri, mime_type)`` for a local image path."""


def guess_mime_type(local_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(local_path)
    return mime_type or "image/png"


def make_browser_use_provider(
    *,
    llm_model: str = "ChatBrowserUse",
    cdp_url: str | None = None,
    use_cloud: bool | None = None,
    cloud_profile_id: str | None = None,
    cloud_proxy_country_code: str | None = None,
    cloud_timeout: int | None = None,
    downloads_path: str | None = None,
) -> BrowserUseProvider:
    """Create the live Browser Use provider used by all storefront snippets."""
    browser_config = BrowserUseBrowserConfig(
        cdp_url=cdp_url,
        use_cloud=use_cloud,
        cloud_profile_id=cloud_profile_id,
        cloud_proxy_country_code=cloud_proxy_country_code,
        cloud_timeout=cloud_timeout,
        downloads_path=downloads_path,
    )
    return BrowserUseProvider(llm_model=llm_model, dry_run=False, browser_config=browser_config)


def make_vertex_veo_client(*, project_id: str, location: str = "global"):
    """Create a Vertex AI GenAI client configured for Veo 3.1."""
    from google import genai

    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    return genai.Client()


@dataclass
class VertexVeo31ReferenceVideoGenerator(VeoGeneratorPort):
    """Veo 3.1 reference-image adapter for avatar + product driven generation.

    This adapter expects a team-provided upload function because the official
    Vertex AI Python examples use Cloud Storage-backed reference images.
    """

    project_id: str
    output_gcs_uri: str
    upload_reference_image: ReferenceImageUploader
    location: str = "global"
    model: str = "veo-3.1-generate-001"
    aspect_ratio: str = "9:16"
    duration_seconds: int = 8
    output_dir: str | Path = Path("output") / "hackathon_videos"

    async def generate_ugc_video(self, bundle: GenerationBundle) -> GeneratedVideoArtifact:
        from google.genai.types import GenerateVideosConfig, Image, VideoGenerationReferenceImage

        artifact_id = f"vid_{uuid4().hex[:12]}"
        output_path = build_output_video_path(artifact_id=artifact_id, output_dir=self.output_dir)
        client = make_vertex_veo_client(project_id=self.project_id, location=self.location)

        # Veo 3.1 supports up to three reference asset images. We use avatar + product,
        # then append any extra deduplicated paths from the bundle if present.
        ordered_paths: list[str] = []
        for candidate in [
            bundle.avatar_image_path,
            bundle.product_image_path,
            *bundle.reference_image_paths,
        ]:
            if candidate and candidate not in ordered_paths:
                ordered_paths.append(candidate)
        reference_paths = ordered_paths[:3]

        refs = []
        for local_path in reference_paths:
            gcs_uri, mime_type = self.upload_reference_image(local_path)
            refs.append(
                VideoGenerationReferenceImage(
                    image=Image(gcs_uri=gcs_uri, mime_type=mime_type),
                    reference_type="asset",
                )
            )

        def _start_operation():
            return client.models.generate_videos(
                model=self.model,
                prompt=bundle.veo_prompt,
                config=GenerateVideosConfig(
                    reference_images=refs,
                    aspect_ratio=self.aspect_ratio,
                    duration_seconds=self.duration_seconds,
                    output_gcs_uri=self.output_gcs_uri,
                ),
            )

        operation = await asyncio.to_thread(_start_operation)
        while not operation.done:
            await asyncio.sleep(15)
            operation = await asyncio.to_thread(client.operations.get, operation)

        result = operation.result
        if not result or not result.generated_videos:
            raise RuntimeError("Veo 3.1 generation returned no videos.")

        video = result.generated_videos[0].video
        video_uri = getattr(video, "uri", None)
        local_video_path: str | None = None
        download_error: str | None = None
        if video_uri:
            try:
                downloaded = await download_video_to_path(video_uri, output_path)
                local_video_path = str(downloaded)
            except Exception as exc:
                download_error = str(exc)
        return GeneratedVideoArtifact(
            artifact_id=artifact_id,
            bundle_id=bundle.bundle_id,
            video_uri=video_uri,
            video_path=local_video_path,
            model_id=self.model,
            reference_image_paths=reference_paths,
            provider_metadata={
                "vertex_output_gcs_uri": self.output_gcs_uri,
                "reference_mode": "asset_images",
                "local_output_path": str(output_path),
                "download_error": download_error,
            },
        )


def build_manual_generation_bundle(
    *,
    avatar_image_path: str,
    product_image_path: str,
    prompt: str,
) -> GenerationBundle:
    """Build a minimal bundle for direct Veo generation without discovery/template steps."""
    prompt_package = build_veo_prompt_package(prompt)
    return GenerationBundle(
        bundle_id=f"manual_{uuid4().hex[:12]}",
        template_id="manual_template",
        product_id="manual_product",
        veo_prompt=prompt_package.full_prompt,
        product_title="manual_product",
        product_description="Use the uploaded product image and any provided description as the source of truth.",
        creative_brief=prompt,
        prompt_package=prompt_package,
        generation_config=VeoGenerationConfig(),
        avatar_image_path=avatar_image_path,
        product_image_path=product_image_path,
        reference_image_paths=[avatar_image_path, product_image_path],
        prior_template_metadata={"source": "manual_browser_use_veo31_snippet"},
    )


def build_live_storefront_stack(
    *,
    db_path: str | Path,
    project_id: str,
    output_gcs_uri: str,
    upload_reference_image: ReferenceImageUploader,
    browser_llm_model: str = "ChatBrowserUse",
    browser_cdp_url: str | None = None,
    browser_use_cloud: bool | None = None,
    cloud_profile_id: str | None = None,
    cloud_proxy_country_code: str | None = None,
    cloud_timeout: int | None = None,
    instascrape_db_path: str | Path | None = None,
):
    """Wire the production-shaped stack once the team snippets are ready."""
    browser = make_browser_use_provider(
        llm_model=browser_llm_model,
        cdp_url=browser_cdp_url,
        use_cloud=browser_use_cloud,
        cloud_profile_id=cloud_profile_id,
        cloud_proxy_country_code=cloud_proxy_country_code,
        cloud_timeout=cloud_timeout,
    )
    gemini = GeminiTemplateAgent(dry_run=False)
    twelve = TwelveLabsUnderstanding(dry_run=False)
    veo = VertexVeo31ReferenceVideoGenerator(
        project_id=project_id,
        output_gcs_uri=output_gcs_uri,
        upload_reference_image=upload_reference_image,
    )
    return build_runtime_stack(
        dry_run=False,
        db_path=db_path,
        instascrape_db_path=instascrape_db_path,
        browser_provider=browser,
        video_understanding=twelve,
        gemini=gemini,
        veo=veo,
    )


async def run_reel_discovery_pipeline(
    *,
    db_path: str | Path,
    project_id: str,
    output_gcs_uri: str,
    upload_reference_image: ReferenceImageUploader,
    browser_cdp_url: str | None = None,
    browser_use_cloud: bool | None = None,
    cloud_profile_id: str | None = None,
    cloud_proxy_country_code: str | None = None,
    cloud_timeout: int | None = None,
    instascrape_db_path: str | Path | None = None,
):
    stack = build_live_storefront_stack(
        db_path=db_path,
        project_id=project_id,
        output_gcs_uri=output_gcs_uri,
        upload_reference_image=upload_reference_image,
        browser_cdp_url=browser_cdp_url,
        browser_use_cloud=browser_use_cloud,
        cloud_profile_id=cloud_profile_id,
        cloud_proxy_country_code=cloud_proxy_country_code,
        cloud_timeout=cloud_timeout,
        instascrape_db_path=instascrape_db_path,
    )
    return await stack.orchestrator.run_reel_to_template_cycle()


async def run_product_discovery_pipeline(
    *,
    db_path: str | Path,
    project_id: str,
    output_gcs_uri: str,
    upload_reference_image: ReferenceImageUploader,
    avatar_image_path: str,
    product_image_path: str,
    niche_query: str = "portable gadgets",
    browser_cdp_url: str | None = None,
    browser_use_cloud: bool | None = None,
    cloud_profile_id: str | None = None,
    cloud_proxy_country_code: str | None = None,
    cloud_timeout: int | None = None,
    instascrape_db_path: str | Path | None = None,
):
    stack = build_live_storefront_stack(
        db_path=db_path,
        project_id=project_id,
        output_gcs_uri=output_gcs_uri,
        upload_reference_image=upload_reference_image,
        browser_cdp_url=browser_cdp_url,
        browser_use_cloud=browser_use_cloud,
        cloud_profile_id=cloud_profile_id,
        cloud_proxy_country_code=cloud_proxy_country_code,
        cloud_timeout=cloud_timeout,
        instascrape_db_path=instascrape_db_path,
    )
    return await stack.orchestrator.run_product_to_video(
        product_image_path=product_image_path,
        avatar_image_path=avatar_image_path,
        niche_query=niche_query,
    )


async def run_social_media_manager(
    *,
    db_path: str | Path,
    project_id: str,
    output_gcs_uri: str,
    upload_reference_image: ReferenceImageUploader,
    media_path: str,
    caption: str,
    template_id: str,
    browser_cdp_url: str | None = None,
    browser_use_cloud: bool | None = None,
    cloud_profile_id: str | None = None,
    cloud_proxy_country_code: str | None = None,
    cloud_timeout: int | None = None,
    instascrape_db_path: str | Path | None = None,
):
    stack = build_live_storefront_stack(
        db_path=db_path,
        project_id=project_id,
        output_gcs_uri=output_gcs_uri,
        upload_reference_image=upload_reference_image,
        browser_cdp_url=browser_cdp_url,
        browser_use_cloud=browser_use_cloud,
        cloud_profile_id=cloud_profile_id,
        cloud_proxy_country_code=cloud_proxy_country_code,
        cloud_timeout=cloud_timeout,
        instascrape_db_path=instascrape_db_path,
    )
    return await stack.orchestrator.run_publish_and_feedback(
        media_path=media_path,
        caption=caption,
        template_id=template_id,
        dry_run=False,
    )


async def run_direct_veo31_generation(
    *,
    project_id: str,
    output_gcs_uri: str,
    upload_reference_image: ReferenceImageUploader,
    avatar_image_path: str,
    product_image_path: str,
    prompt: str,
) -> GeneratedVideoArtifact:
    """Direct path: avatar image + prompt + product image -> Veo 3.1 -> video output."""
    veo = VertexVeo31ReferenceVideoGenerator(
        project_id=project_id,
        output_gcs_uri=output_gcs_uri,
        upload_reference_image=upload_reference_image,
    )
    bundle = build_manual_generation_bundle(
        avatar_image_path=avatar_image_path,
        product_image_path=product_image_path,
        prompt=prompt,
    )
    return await veo.generate_ugc_video(bundle)


async def run_entire_storefront_pipeline(
    *,
    db_path: str | Path,
    project_id: str,
    output_gcs_uri: str,
    upload_reference_image: ReferenceImageUploader,
    avatar_image_path: str,
    product_image_path: str,
    media_path: str,
    niche_query: str = "portable gadgets",
    caption: str = "Auto-generated Instagram storefront reel",
    browser_cdp_url: str | None = None,
    browser_use_cloud: bool | None = None,
    cloud_profile_id: str | None = None,
    cloud_proxy_country_code: str | None = None,
    cloud_timeout: int | None = None,
    instascrape_db_path: str | Path | None = None,
):
    stack = build_live_storefront_stack(
        db_path=db_path,
        project_id=project_id,
        output_gcs_uri=output_gcs_uri,
        upload_reference_image=upload_reference_image,
        browser_cdp_url=browser_cdp_url,
        browser_use_cloud=browser_use_cloud,
        cloud_profile_id=cloud_profile_id,
        cloud_proxy_country_code=cloud_proxy_country_code,
        cloud_timeout=cloud_timeout,
        instascrape_db_path=instascrape_db_path,
    )
    return await stack.orchestrator.run_closed_loop_cycle(
        product_image_path=product_image_path,
        avatar_image_path=avatar_image_path,
        niche_query=niche_query,
        caption=caption,
        media_path=media_path,
        dry_run=False,
    )


def example_upload_reference_image(local_path: str) -> tuple[str, str]:
    """Example seam only.

    Replace this with the team's uploader once they finish the storage snippet.
    """
    path = Path(local_path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    gcs_uri = f"gs://replace-with-your-bucket/reference-assets/{path.name}"
    return gcs_uri, guess_mime_type(str(path))


async def run_demo_local_generation(
    *,
    avatar_image_path: str,
    product_image_path: str,
    prompt: str,
    output_dir: str | Path = Path("output") / "hackathon_videos",
) -> GeneratedVideoArtifact:
    """Create a local demo mp4 from the avatar/product assets without calling Veo."""

    bundle = build_manual_generation_bundle(
        avatar_image_path=avatar_image_path,
        product_image_path=product_image_path,
        prompt=prompt,
    )
    artifact_id = f"demo_{uuid4().hex[:12]}"
    output_path = build_output_video_path(artifact_id=artifact_id, output_dir=output_dir)
    render_demo_bundle_video(bundle=bundle, output_path=output_path)
    return GeneratedVideoArtifact(
        artifact_id=artifact_id,
        bundle_id=bundle.bundle_id,
        video_uri=None,
        video_path=str(output_path),
        model_id="local-demo-render",
        reference_image_paths=list(bundle.reference_image_paths),
        provider_metadata={"mode": "local_demo", "prompt": prompt},
    )
