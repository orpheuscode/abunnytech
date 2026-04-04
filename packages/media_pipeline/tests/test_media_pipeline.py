from __future__ import annotations

import json
from pathlib import Path

from media_pipeline.audio_elevenlabs import build_elevenlabs_request
from media_pipeline.captions import build_caption_metadata
from media_pipeline.export import write_stage2_dry_run_bundle
from media_pipeline.models import PostProductionManifest
from media_pipeline.postprod_manifest import build_post_production_manifest
from media_pipeline.redo import apply_redo_and_directives
from media_pipeline.script_adaptation import adapt_script_from_blueprint
from media_pipeline.variants import build_variant_content_packages

from pipeline_contracts.models import (
    IdentityMatrix,
    OptimizationDirectiveEnvelope,
    RedoQueueItem,
    VideoBlueprint,
)
from pipeline_contracts.models.common import Envelope
from pipeline_contracts.models.enums import DirectiveTargetStage, RedoReasonCode
from pipeline_contracts.models.identity import AvatarPackRef, PersonaAxis, VoicePackRef


def _sample_blueprint(**kwargs: object) -> VideoBlueprint:
    base = dict(
        blueprint_id="vb_fixture",
        matrix_id="mx_fixture",
        title="Fixture tip",
        hook="You need this hack.",
        outline=["Problem", "Fix", "Proof"],
        suggested_caption="Try this today",
        hashtags=["tips"],
        audio_id="trend_001",
        duration_seconds_target=30,
    )
    base.update(kwargs)
    return VideoBlueprint.model_validate(base)


def _sample_identity() -> IdentityMatrix:
    return IdentityMatrix(
        matrix_id="mx_fixture",
        display_name="Fixture Creator",
        niche="productivity",
        persona=PersonaAxis(
            tone="upbeat",
            topics=["habits"],
            avoid_topics=["politics"],
            disclosure_line="Demo account.",
        ),
        avatar=AvatarPackRef(avatar_id="av_1"),
        voice=VoicePackRef(voice_id="voice_11labs_1"),
    )


def test_adapted_script_durations_sum_to_target() -> None:
    bp = _sample_blueprint(duration_seconds_target=20)
    script = adapt_script_from_blueprint(bp)
    assert abs(sum(s.duration_seconds for s in script.segments) - 20.0) < 0.02
    assert script.segments[0].role == "hook"
    assert script.segments[-1].role == "cta"
    assert "hook" in [s.role for s in script.segments]
    assert script.full_voiceover_text


def test_redo_updates_hook() -> None:
    bp = _sample_blueprint()
    redo = [
        RedoQueueItem(
            item_id="r1",
            reason="tighter hook",
            reason_code=RedoReasonCode.QUALITY,
            blueprint_id="vb_fixture",
            payload={"new_hook": "Revised hook line."},
        )
    ]
    out = apply_redo_and_directives(bp, redo_items=redo)
    assert out.hook == "Revised hook line."


def test_directive_stage2_updates_outline() -> None:
    bp = _sample_blueprint()
    d = OptimizationDirectiveEnvelope(
        directive_id="d1",
        target_stages=[DirectiveTargetStage.STAGE2],
        envelope=Envelope(schema_version="1", payload={"replace_outline": ["A", "B"]}),
    )
    out = apply_redo_and_directives(bp, directives=[d])
    assert out.outline == ["A", "B"]


def test_elevenlabs_request_uses_voice_and_script() -> None:
    bp = _sample_blueprint()
    script = adapt_script_from_blueprint(bp)
    req = build_elevenlabs_request(script, "v123")
    assert req.voice_id == "v123"
    assert len(req.text) > 0


def test_postprod_manifest_trending_underlay_when_audio_id() -> None:
    bp = _sample_blueprint(audio_id="aud_x")
    script = adapt_script_from_blueprint(bp)
    m = build_post_production_manifest(
        bp,
        script,
        raw_video_placeholder="/tmp/raw.mp4",
        voiceover_placeholder="/tmp/vo.mp3",
        output_video_placeholder="/tmp/out.mp4",
        subtitles_path_placeholder="/tmp/subs.srt",
        trending_audio_id=bp.audio_id,
    )
    assert m.audio_underlay.mode == "trending"
    assert m.audio_underlay.trending_audio_id == "aud_x"
    assert m.crop.target_aspect == "9:16"


def test_variant_packages_include_primary_and_slides() -> None:
    bp = _sample_blueprint()
    idm = _sample_identity()
    pkgs = build_variant_content_packages(
        bp,
        idm,
        "run_1",
        artifact_base_dir="/tmp/variants",
        carousel_slide_count=2,
        story_frame_count=1,
    )
    assert len(pkgs) == 4
    assert pkgs[0].primary_video.mime_type == "video/mp4"
    assert pkgs[1].primary_video.mime_type == "image/png"


def test_dry_run_bundle_writes_json(tmp_path: Path) -> None:
    bp = _sample_blueprint()
    script = adapt_script_from_blueprint(bp)
    from media_pipeline.video_nano_banana import build_nano_banana_request

    nb = build_nano_banana_request(bp, _sample_identity(), script)
    el = build_elevenlabs_request(script, "v1")
    post = build_post_production_manifest(
        bp,
        script,
        raw_video_placeholder="raw",
        voiceover_placeholder="vo",
        output_video_placeholder="out",
        subtitles_path_placeholder="sub",
        trending_audio_id=None,
    )
    paths = write_stage2_dry_run_bundle(
        tmp_path,
        adapted_script=script,
        elevenlabs=el,
        nano_banana=nb,
        postprod=post,
        caption_meta={"caption": "x"},
        asset_manifest={"k": "v"},
    )
    for p in paths.values():
        assert Path(p).is_file()
    data = json.loads(Path(paths["post_production_manifest"]).read_text(encoding="utf-8"))
    PostProductionManifest.model_validate(data)


def test_caption_metadata_includes_disclosure() -> None:
    bp = _sample_blueprint()
    script = adapt_script_from_blueprint(bp)
    meta = build_caption_metadata(bp, _sample_identity(), script)
    assert "Demo account" in meta.caption
