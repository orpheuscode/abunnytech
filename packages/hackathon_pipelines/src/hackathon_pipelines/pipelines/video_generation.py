"""Video generation: Gemini-assembled Veo prompt + reference images → Veo 3.1 artifact."""

from __future__ import annotations

from hackathon_pipelines.contracts import (
    GeneratedVideoArtifact,
    GenerationBundle,
    ProductCandidate,
    VideoTemplateRecord,
)
from hackathon_pipelines.ports import GeminiVideoAgentPort, VeoGeneratorPort


class VideoGenerationPipeline:
    def __init__(self, *, gemini: GeminiVideoAgentPort, veo: VeoGeneratorPort) -> None:
        self._gemini = gemini
        self._veo = veo

    async def generate_for_product(
        self,
        template: VideoTemplateRecord,
        product: ProductCandidate,
        *,
        product_image_path: str,
        avatar_image_path: str,
    ) -> tuple[GenerationBundle, GeneratedVideoArtifact]:
        bundle = await self._gemini.build_generation_bundle(
            template,
            product,
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
        )
        artifact = await self._veo.generate_ugc_video(bundle)
        return bundle, artifact
