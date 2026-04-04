from __future__ import annotations

import uuid
from enum import StrEnum

from media_pipeline.captions import build_caption_metadata
from media_pipeline.script_adaptation import adapt_script_from_blueprint
from pipeline_contracts.models import ContentPackage, IdentityMatrix, MediaAssetRef, VideoBlueprint


class VariantKind(StrEnum):
    PRIMARY_SHORT = "primary_short"
    CAROUSEL_SLIDE = "carousel_slide"
    STORY_FRAME = "story_frame"


def build_variant_content_packages(
    blueprint: VideoBlueprint,
    identity: IdentityMatrix,
    run_id: str,
    *,
    artifact_base_dir: str,
    carousel_slide_count: int = 0,
    story_frame_count: int = 0,
) -> list[ContentPackage]:
    """
    Build additional ContentPackage rows for carousel slides and story frames.

    Each variant uses a distinct ``package_id`` and MIME type (image for static slides).
    The first package in the returned list is always the primary short (video placeholder).
    """
    script = adapt_script_from_blueprint(blueprint)
    meta = build_caption_metadata(blueprint, identity, script)

    primary_path = f"{artifact_base_dir.rstrip('/')}/primary_short.mp4"
    primary = ContentPackage(
        package_id=f"cp_{uuid.uuid4().hex[:12]}",
        run_id=run_id,
        blueprint_id=blueprint.blueprint_id,
        matrix_id=identity.matrix_id,
        primary_video=MediaAssetRef(path=primary_path, mime_type="video/mp4", bytes_approx=0),
        caption=meta.caption,
        hashtags=meta.hashtags,
        disclosure_tag="#AIcreatorDemo",
    )

    out: list[ContentPackage] = [primary]

    for i in range(max(carousel_slide_count, 0)):
        slide_path = f"{artifact_base_dir.rstrip('/')}/carousel_{i:02d}.png"
        cap = f"{meta.caption}\n\n(Carousel {i + 1}/{carousel_slide_count})".strip()
        out.append(
            ContentPackage(
                package_id=f"cp_{uuid.uuid4().hex[:12]}",
                run_id=run_id,
                blueprint_id=blueprint.blueprint_id,
                matrix_id=identity.matrix_id,
                primary_video=MediaAssetRef(path=slide_path, mime_type="image/png", bytes_approx=0),
                caption=cap,
                hashtags=meta.hashtags,
                disclosure_tag=primary.disclosure_tag,
            )
        )

    for i in range(max(story_frame_count, 0)):
        frame_path = f"{artifact_base_dir.rstrip('/')}/story_{i:02d}.png"
        cap = f"{meta.caption}\n\n(Story frame {i + 1})".strip()
        out.append(
            ContentPackage(
                package_id=f"cp_{uuid.uuid4().hex[:12]}",
                run_id=run_id,
                blueprint_id=blueprint.blueprint_id,
                matrix_id=identity.matrix_id,
                primary_video=MediaAssetRef(path=frame_path, mime_type="image/png", bytes_approx=0),
                caption=cap,
                hashtags=meta.hashtags,
                disclosure_tag=primary.disclosure_tag,
            )
        )

    return out
