from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from media_pipeline.audio_elevenlabs import (
    AudioSynthesisAdapter,
    MockElevenLabsAdapter,
    build_elevenlabs_request,
)
from media_pipeline.captions import build_caption_metadata
from media_pipeline.export import write_minimal_srt_stub, write_stage2_dry_run_bundle
from media_pipeline.postprod_manifest import build_post_production_manifest
from media_pipeline.redo import apply_redo_and_directives
from media_pipeline.script_adaptation import adapt_script_from_blueprint
from media_pipeline.variants import build_variant_content_packages
from media_pipeline.video_nano_banana import MockNanoBananaAdapter, build_nano_banana_request

from abunny_stage2_generation.render_port import VideoRenderPort
from pipeline_contracts.models import (
    ContentPackage,
    IdentityMatrix,
    MediaAssetRef,
    OptimizationDirectiveEnvelope,
    RedoQueueItem,
    VideoBlueprint,
)
from pipeline_core.audit import AuditLogger
from pipeline_core.repository import RunRepository
from pipeline_core.settings import Settings


@dataclass(frozen=True)
class Stage2GenerationResult:
    """Stage 2 output: primary handoff package plus optional variant packages."""

    primary_package: ContentPackage
    variant_packages: list[ContentPackage]
    manifest_paths: dict[str, str]
    adapted_script_dump: dict[str, Any]


def _load_redo(repo: RunRepository, run_id: str) -> list[RedoQueueItem]:
    raw = repo.get_artifact(run_id, "redo_queue")
    if not raw or not isinstance(raw, list):
        return []
    return [RedoQueueItem.model_validate(x) for x in raw]


def _load_directives(repo: RunRepository, run_id: str) -> list[OptimizationDirectiveEnvelope]:
    raw = repo.get_artifact(run_id, "optimization_directives")
    if not raw or not isinstance(raw, list):
        return []
    return [OptimizationDirectiveEnvelope.model_validate(x) for x in raw]


def run_stage2_generation(
    run_id: str,
    repo: RunRepository,
    audit: AuditLogger,
    settings: Settings,
    renderer: VideoRenderPort,
    *,
    blueprint: VideoBlueprint,
    identity: IdentityMatrix,
    tts: AudioSynthesisAdapter | None = None,
    carousel_slide_count: int = 0,
    story_frame_count: int = 0,
) -> Stage2GenerationResult:
    """
    Full Stage 2: redo/directive merge, script/caption/manifests, optional mocks, ContentPackage(s).

    Primary ``ContentPackage`` remains the official short; carousel/story rows are additional
    packages with image placeholders for downstream schedulers.
    """
    tts = tts or MockElevenLabsAdapter()
    redo = _load_redo(repo, run_id)
    directives = _load_directives(repo, run_id)
    blueprint_eff = apply_redo_and_directives(blueprint, redo_items=redo, directives=directives)

    script = adapt_script_from_blueprint(blueprint_eff)
    cap_meta = build_caption_metadata(blueprint_eff, identity, script)
    el_req = build_elevenlabs_request(script, identity.voice.voice_id)
    nb_req = build_nano_banana_request(blueprint_eff, identity, script)

    out_dir = settings.artifacts_dir / run_id / "stage2"
    out_dir.mkdir(parents=True, exist_ok=True)
    primary_path = out_dir / "primary_demo.mp4"
    raw_vid_path = out_dir / "raw_generated.bin"
    vo_path = out_dir / "voiceover.bin"
    srt_path = out_dir / "subtitles.srt"

    write_minimal_srt_stub(srt_path, script)

    trending_id = blueprint_eff.audio_id
    postprod = build_post_production_manifest(
        blueprint_eff,
        script,
        raw_video_placeholder=str(raw_vid_path.resolve()),
        voiceover_placeholder=str(vo_path.resolve()),
        output_video_placeholder=str(primary_path.resolve()),
        subtitles_path_placeholder=str(srt_path.resolve()),
        trending_audio_id=trending_id,
    )

    audit.log(
        run_id,
        "stage2",
        "generation_started",
        {
            "blueprint_id": blueprint_eff.blueprint_id,
            "dry_run": settings.dry_run,
            "carousel_slides": carousel_slide_count,
            "story_frames": story_frame_count,
        },
    )

    manifest_paths: dict[str, str] = {}
    if settings.dry_run:
        asset_manifest = {
            "run_id": run_id,
            "blueprint_id": blueprint_eff.blueprint_id,
            "placeholders": {
                "raw_video": str(raw_vid_path.resolve()),
                "voiceover": str(vo_path.resolve()),
                "primary_mp4": str(primary_path.resolve()),
                "subtitles_srt": str(srt_path.resolve()),
            },
            "trending_audio_id": trending_id,
            "variant_counts": {
                "carousel_slides": carousel_slide_count,
                "story_frames": story_frame_count,
            },
        }
        manifest_paths = write_stage2_dry_run_bundle(
            out_dir,
            adapted_script=script,
            elevenlabs=el_req,
            nano_banana=nb_req,
            postprod=postprod,
            caption_meta={
                "caption": cap_meta.caption,
                "hashtags": cap_meta.hashtags,
                "title_for_upload": cap_meta.title_for_upload,
                "alt_text": cap_meta.alt_text,
            },
            asset_manifest=asset_manifest,
        )
        # Still synthesize placeholder paths so adapters stay exercised without network
        MockNanoBananaAdapter().generate_to_path(nb_req, raw_vid_path, dry_run=True)
        tts.synthesize_to_path(el_req, vo_path, dry_run=True)
        media = MediaAssetRef(path=str(primary_path.resolve()), mime_type="video/mp4", bytes_approx=0)
        primary_path.write_text(
            "DRY_RUN_PRIMARY_VIDEO_PLACEHOLDER\n",
            encoding="utf-8",
        )
    else:
        MockNanoBananaAdapter().generate_to_path(nb_req, raw_vid_path, dry_run=False)
        tts.synthesize_to_path(el_req, vo_path, dry_run=False)
        final_path = renderer.render(blueprint_eff, primary_path, dry_run=False)
        try:
            size = final_path.stat().st_size
        except OSError:
            size = None
        media = MediaAssetRef(
            path=str(final_path.resolve()),
            mime_type="video/mp4",
            bytes_approx=size,
        )
        manifest_paths = write_stage2_dry_run_bundle(
            out_dir,
            adapted_script=script,
            elevenlabs=el_req,
            nano_banana=nb_req,
            postprod=postprod,
            caption_meta={
                "caption": cap_meta.caption,
                "hashtags": cap_meta.hashtags,
                "title_for_upload": cap_meta.title_for_upload,
                "alt_text": cap_meta.alt_text,
            },
            asset_manifest={
                "run_id": run_id,
                "blueprint_id": blueprint_eff.blueprint_id,
                "resolved_paths": {
                    "raw_video": str(raw_vid_path.resolve()),
                    "voiceover": str(vo_path.resolve()),
                    "primary_mp4": str(media.path),
                },
            },
        )

    disclosure = "#AIcreatorDemo"
    if settings.disclosure_demo and identity.persona.disclosure_line:
        disclosure = f"{disclosure} {identity.persona.disclosure_line}"

    primary = ContentPackage(
        package_id=f"cp_{uuid.uuid4().hex[:12]}",
        run_id=run_id,
        blueprint_id=blueprint_eff.blueprint_id,
        matrix_id=identity.matrix_id,
        primary_video=media,
        caption=cap_meta.caption,
        hashtags=cap_meta.hashtags,
        disclosure_tag=disclosure,
    )

    variant_base = str((settings.artifacts_dir / run_id / "variants").resolve())
    variants = build_variant_content_packages(
        blueprint_eff,
        identity,
        run_id,
        artifact_base_dir=variant_base,
        carousel_slide_count=carousel_slide_count,
        story_frame_count=story_frame_count,
    )
    merged_variants = [primary]
    for p in variants[1:]:
        merged_variants.append(p.model_copy(update={"disclosure_tag": primary.disclosure_tag}))

    audit.log(
        run_id,
        "stage2",
        "content_package_ready",
        {"package_id": primary.package_id, "path": media.path, "variant_count": len(merged_variants)},
    )

    return Stage2GenerationResult(
        primary_package=primary,
        variant_packages=merged_variants,
        manifest_paths=manifest_paths,
        adapted_script_dump=script.model_dump(mode="json"),
    )
