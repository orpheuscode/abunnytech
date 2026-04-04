from __future__ import annotations

import uuid

from pipeline_contracts.models import (
    IdentityMatrix,
    OptimizationDirectiveEnvelope,
    RedoQueueItem,
    VideoBlueprint,
)
from pipeline_core.audit import AuditLogger
from pipeline_core.repository import RunRepository
from pipeline_core.settings import Settings
from pipeline_stage1_discover.adapters import DiscoveryProvider


def _load_identity(repo: RunRepository, run_id: str) -> IdentityMatrix:
    raw = repo.get_artifact(run_id, "identity_matrix")
    if not raw:
        raise ValueError("identity_matrix missing — run stage0 first")
    return IdentityMatrix.model_validate(raw)


def _optional_directives(repo: RunRepository, run_id: str) -> list[OptimizationDirectiveEnvelope]:
    raw = repo.get_artifact(run_id, "optimization_directives")
    if not raw or not isinstance(raw, list):
        return []
    return [OptimizationDirectiveEnvelope.model_validate(x) for x in raw]


def _optional_redo(repo: RunRepository, run_id: str) -> list[RedoQueueItem]:
    raw = repo.get_artifact(run_id, "redo_queue")
    if not raw or not isinstance(raw, list):
        return []
    return [RedoQueueItem.model_validate(x) for x in raw]


def run_stage1(
    run_id: str,
    repo: RunRepository,
    audit: AuditLogger,
    settings: Settings,
    discovery: DiscoveryProvider,
) -> VideoBlueprint:
    identity = _load_identity(repo, run_id)
    _optional_directives(repo, run_id)
    redo = _optional_redo(repo, run_id)

    trending = discovery.fetch_trending_audio(identity.niche)
    competitors = discovery.fetch_competitors(identity.niche)

    chosen_audio = trending[0] if trending else None
    hook_extra = ""
    if competitors and competitors[0].recent_hook_pattern:
        hook_extra = f" Inspired by pattern: {competitors[0].recent_hook_pattern}"
    if redo:
        hook_extra += f" | Redo hints: {redo[0].reason}"

    blueprint = VideoBlueprint(
        blueprint_id=f"vb_{uuid.uuid4().hex[:12]}",
        matrix_id=identity.matrix_id,
        title=f"{identity.display_name} — {identity.niche} quick tip",
        hook=f"Stop scrolling — 3 things about {identity.niche}.{hook_extra}",
        outline=[
            "Hook + problem",
            "Three bullets with on-screen text",
            "CTA + disclosure",
        ],
        suggested_caption=f"{identity.persona.disclosure_line or ''} #{identity.niche.replace(' ', '')}",
        hashtags=[identity.niche.replace(" ", "")[:20], "learnontiktok", "tips"],
        audio_id=chosen_audio.audio_id if chosen_audio else None,
        duration_seconds_target=15,
    )

    audit.log(
        run_id,
        "stage1",
        "blueprint_drafted",
        {
            "blueprint_id": blueprint.blueprint_id,
            "trending_count": len(trending),
            "competitor_count": len(competitors),
            "dry_run": settings.dry_run,
        },
    )

    repo.set_artifact(run_id, "trending_audio", [t.model_dump(mode="json") for t in trending])
    repo.set_artifact(run_id, "competitor_watch", [c.model_dump(mode="json") for c in competitors])
    repo.set_artifact(run_id, "video_blueprint", blueprint.model_dump(mode="json"))

    return blueprint
