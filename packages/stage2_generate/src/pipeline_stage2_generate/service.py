from __future__ import annotations

from abunny_stage2_generation.pipeline import run_stage2_generation

from pipeline_contracts.models import ContentPackage, IdentityMatrix, VideoBlueprint
from pipeline_core.audit import AuditLogger
from pipeline_core.repository import RunRepository
from pipeline_core.settings import Settings
from pipeline_stage2_generate.adapters import VideoRenderProvider


def _load_identity(repo: RunRepository, run_id: str) -> IdentityMatrix:
    raw = repo.get_artifact(run_id, "identity_matrix")
    if not raw:
        raise ValueError("identity_matrix missing — run stage0 first")
    return IdentityMatrix.model_validate(raw)


def _load_blueprint(repo: RunRepository, run_id: str) -> VideoBlueprint:
    raw = repo.get_artifact(run_id, "video_blueprint")
    if not raw:
        raise ValueError("video_blueprint missing — run stage1 first")
    return VideoBlueprint.model_validate(raw)


def run_stage2(
    run_id: str,
    repo: RunRepository,
    audit: AuditLogger,
    settings: Settings,
    renderer: VideoRenderProvider,
) -> ContentPackage:
    identity = _load_identity(repo, run_id)
    blueprint = _load_blueprint(repo, run_id)

    result = run_stage2_generation(
        run_id,
        repo,
        audit,
        settings,
        renderer,
        blueprint=blueprint,
        identity=identity,
        carousel_slide_count=0,
        story_frame_count=0,
    )

    repo.set_artifact(run_id, "content_package", result.primary_package.model_dump(mode="json"))
    repo.set_artifact(
        run_id,
        "stage2_variant_packages",
        {"packages": [p.model_dump(mode="json") for p in result.variant_packages]},
    )

    return result.primary_package
