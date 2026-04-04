"""
Fixture-driven Stage 2 dry-run: writes content package JSON and adapter manifests.

Run from repo root:
  uv run python examples/stage2/run_dry_run.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from media_pipeline.audio_elevenlabs import build_elevenlabs_request  # noqa: E402
from media_pipeline.captions import build_caption_metadata  # noqa: E402
from media_pipeline.export import write_minimal_srt_stub, write_stage2_dry_run_bundle  # noqa: E402
from media_pipeline.postprod_manifest import build_post_production_manifest  # noqa: E402
from media_pipeline.redo import apply_redo_and_directives  # noqa: E402
from media_pipeline.script_adaptation import adapt_script_from_blueprint  # noqa: E402
from media_pipeline.variants import build_variant_content_packages  # noqa: E402
from media_pipeline.video_nano_banana import build_nano_banana_request  # noqa: E402

from pipeline_contracts.models import (  # noqa: E402
    IdentityMatrix,
    MediaAssetRef,
    OptimizationDirectiveEnvelope,
    RedoQueueItem,
    VideoBlueprint,
)
from pipeline_contracts.models.common import Envelope  # noqa: E402
from pipeline_contracts.models.enums import DirectiveTargetStage  # noqa: E402


def main() -> None:
    here = Path(__file__).resolve().parent
    fx = here / "fixtures"
    out = here / "out"
    out.mkdir(parents=True, exist_ok=True)

    bp = VideoBlueprint.model_validate_json((fx / "video_blueprint.json").read_text(encoding="utf-8"))
    identity = IdentityMatrix.model_validate_json((fx / "identity_matrix.json").read_text(encoding="utf-8"))
    redo_raw = json.loads((fx / "redo_queue.json").read_text(encoding="utf-8"))
    redo = [RedoQueueItem.model_validate(x) for x in redo_raw]

    directives = [
        OptimizationDirectiveEnvelope(
            directive_id="dir_fixture_caps",
            target_stages=[DirectiveTargetStage.STAGE2],
            envelope=Envelope(
                schema_version="1",
                payload={"new_title": "Fixture title from directive"},
            ),
        )
    ]

    bp_eff = apply_redo_and_directives(bp, redo_items=redo, directives=directives)
    script = adapt_script_from_blueprint(bp_eff)
    cap = build_caption_metadata(bp_eff, identity, script)
    el = build_elevenlabs_request(script, identity.voice.voice_id)
    nb = build_nano_banana_request(bp_eff, identity, script)

    run_id = f"example_{uuid.uuid4().hex[:10]}"
    stage2_dir = out / "artifacts" / run_id / "stage2"
    stage2_dir.mkdir(parents=True, exist_ok=True)
    srt = stage2_dir / "subtitles.srt"
    write_minimal_srt_stub(srt, script)

    post = build_post_production_manifest(
        bp_eff,
        script,
        raw_video_placeholder=str((stage2_dir / "raw_generated.bin").resolve()),
        voiceover_placeholder=str((stage2_dir / "voiceover.bin").resolve()),
        output_video_placeholder=str((stage2_dir / "primary_demo.mp4").resolve()),
        subtitles_path_placeholder=str(srt.resolve()),
        trending_audio_id=bp_eff.audio_id,
    )

    asset_manifest = {
        "run_id": run_id,
        "blueprint_id": bp_eff.blueprint_id,
        "placeholders": {
            "raw_video": post.input_video_placeholder,
            "voiceover": post.voiceover_audio_placeholder,
            "primary_mp4": post.output_video_placeholder,
            "subtitles_srt": str(srt.resolve()),
        },
        "trending_audio_id": bp_eff.audio_id,
    }

    paths = write_stage2_dry_run_bundle(
        stage2_dir,
        adapted_script=script,
        elevenlabs=el,
        nano_banana=nb,
        postprod=post,
        caption_meta={
            "caption": cap.caption,
            "hashtags": cap.hashtags,
            "title_for_upload": cap.title_for_upload,
            "alt_text": cap.alt_text,
        },
        asset_manifest=asset_manifest,
    )

    variant_base = str((out / "artifacts" / run_id / "variants").resolve())
    packages = build_variant_content_packages(
        bp_eff,
        identity,
        run_id,
        artifact_base_dir=variant_base,
        carousel_slide_count=3,
        story_frame_count=2,
    )
    primary = packages[0]
    primary_path = str((stage2_dir / "primary_demo.mp4").resolve())
    primary_pkg = primary.model_copy(
        update={
            "primary_video": MediaAssetRef(path=primary_path, mime_type="video/mp4", bytes_approx=0),
            "caption": cap.caption,
            "hashtags": cap.hashtags,
        }
    )
    all_pkgs = [primary_pkg, *packages[1:]]

    (out / "content_package.primary.json").write_text(
        json.dumps(primary_pkg.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "content_packages.all.json").write_text(
        json.dumps([p.model_dump(mode="json") for p in all_pkgs], indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "manifest_paths.json").write_text(json.dumps(paths, indent=2) + "\n", encoding="utf-8")
    print("Wrote:", out / "content_package.primary.json")
    print("Manifests:", paths)


if __name__ == "__main__":
    main()
