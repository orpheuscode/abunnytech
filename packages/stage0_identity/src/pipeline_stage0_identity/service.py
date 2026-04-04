from __future__ import annotations

import uuid
from dataclasses import dataclass

from pipeline_contracts.models.identity import (
    AvatarPackRef,
    IdentityMatrix,
    PersonaAxis,
    TrainingMaterialItem,
    TrainingMaterialsManifest,
    VoicePackRef,
)
from pipeline_core.audit import AuditLogger
from pipeline_core.repository import RunRepository
from pipeline_core.settings import Settings


@dataclass
class IdentityStageInput:
    display_name: str
    niche: str
    tone: str
    topics: list[str] | None = None
    avatar_provider: str = "mock"
    voice_provider: str = "mock"


def run_stage0(
    run_id: str,
    inp: IdentityStageInput,
    repo: RunRepository,
    audit: AuditLogger,
    settings: Settings,
) -> tuple[IdentityMatrix, TrainingMaterialsManifest]:
    matrix_id = f"im_{uuid.uuid4().hex[:12]}"
    persona = PersonaAxis(
        tone=inp.tone,
        topics=inp.topics or [],
        avoid_topics=[],
        disclosure_line="Sandbox AI demo — not a human impersonation.",
    )
    identity = IdentityMatrix(
        matrix_id=matrix_id,
        display_name=inp.display_name,
        niche=inp.niche,
        persona=persona,
        avatar=AvatarPackRef(avatar_id=f"av_{matrix_id}", provider=inp.avatar_provider),
        voice=VoicePackRef(voice_id=f"vo_{matrix_id}", provider=inp.voice_provider),
    )
    manifest = TrainingMaterialsManifest(
        manifest_id=f"tm_{uuid.uuid4().hex[:12]}",
        matrix_id=matrix_id,
        items=[
            TrainingMaterialItem(
                uri="fixture://style-card-v1",
                kind="style_ref",
                label="Brand style card (fixture)",
            ),
            TrainingMaterialItem(
                uri="fixture://sample-lines",
                kind="transcript",
                label="Voice sample lines (fixture)",
            ),
        ],
    )

    audit.log(
        run_id,
        "stage0",
        "identity_built",
        {"matrix_id": matrix_id, "dry_run": settings.dry_run},
    )

    repo.set_artifact(run_id, "identity_matrix", identity.model_dump(mode="json"))
    repo.set_artifact(run_id, "training_materials_manifest", manifest.model_dump(mode="json"))

    return identity, manifest
