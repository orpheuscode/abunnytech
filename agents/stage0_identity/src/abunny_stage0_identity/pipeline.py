from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from abunny_stage0_identity.adapters.nano_banana import register_visual_assets
from abunny_stage0_identity.compiler import IdentityMatrixCompiler
from abunny_stage0_identity.models_input import PersonaSetup
from abunny_stage0_identity.system_prompt import build_system_prompt
from pipeline_contracts.models.enums import TrainingMaterialKind
from pipeline_contracts.models.identity import (
    IdentityMatrix,
    TrainingMaterialItem,
    TrainingMaterialsManifest,
)


@dataclass
class Stage0CompileResult:
    identity: IdentityMatrix
    training_manifest: TrainingMaterialsManifest
    asset_manifest: dict[str, Any]
    system_prompt: str


def _training_manifest(
    matrix_id: str,
    identity: IdentityMatrix,
    setup: PersonaSetup,
    visual_summary: dict[str, Any],
) -> TrainingMaterialsManifest:
    manifest_id = f"tm_{uuid.uuid4().hex[:12]}"
    voice_uri = str(identity.voice.sample_url) if identity.voice.sample_url else "fixture://voice-sample"
    preview_uri = str(identity.avatar.preview_url) if identity.avatar.preview_url else "fixture://avatar-preview"
    items: list[TrainingMaterialItem] = [
        TrainingMaterialItem(
            uri=preview_uri,
            kind=TrainingMaterialKind.STYLE_REF,
            label="Avatar / character preview (registered asset)",
        ),
        TrainingMaterialItem(
            uri=voice_uri,
            kind=TrainingMaterialKind.TRANSCRIPT,
            label="Voice sample (line read or timbre reference)",
        ),
        TrainingMaterialItem(
            uri="fixture://system-prompt-md",
            kind=TrainingMaterialKind.DOCUMENT,
            label="system_prompt.md (persona brief for LLM stages)",
        ),
    ]
    if visual_summary.get("palette"):
        items.append(
            TrainingMaterialItem(
                uri="fixture://visual-style-card",
                kind=TrainingMaterialKind.STYLE_REF,
                label="Visual style card (palette / lighting / camera)",
            )
        )
    return TrainingMaterialsManifest(
        manifest_id=manifest_id,
        matrix_id=matrix_id,
        items=items,
    )


def _asset_manifest(
    matrix_id: str,
    identity: IdentityMatrix,
    setup: PersonaSetup,
    *,
    dry_run: bool,
    visual_summary: dict[str, Any],
) -> dict[str, Any]:
    manifest_id = f"am_{uuid.uuid4().hex[:12]}"
    nb_rows = register_visual_assets(
        matrix_id=matrix_id,
        dry_run=dry_run,
        collection_hint=setup.integrations.nano_banana_collection_id,
        visual_summary=visual_summary,
    )
    assets: list[dict[str, Any]] = [
        {
            "kind": "avatar",
            "provider": identity.avatar.provider,
            "external_ref": identity.avatar.avatar_id,
            "status": "stub" if dry_run else "pending",
            "metadata": {"preview_url": str(identity.avatar.preview_url)}
            if identity.avatar.preview_url
            else {},
        },
        {
            "kind": "voice",
            "provider": identity.voice.provider,
            "external_ref": identity.voice.voice_id,
            "status": "stub" if dry_run else "pending",
            "metadata": {"sample_url": str(identity.voice.sample_url)}
            if identity.voice.sample_url
            else {},
        },
    ]
    assets.extend(nb_rows)
    return {
        "manifest_id": manifest_id,
        "matrix_id": matrix_id,
        "dry_run": dry_run,
        "assets": assets,
    }


def compile_stage0(setup: PersonaSetup, *, dry_run: bool, matrix_id: str | None = None) -> Stage0CompileResult:
    mid = matrix_id or f"im_{uuid.uuid4().hex[:12]}"
    compiler = IdentityMatrixCompiler(setup, dry_run=dry_run)
    identity = compiler.compile_identity_matrix(mid)
    visual_summary = compiler.normalize_visual_style()
    training = _training_manifest(mid, identity, setup, visual_summary)
    assets = _asset_manifest(mid, identity, setup, dry_run=dry_run, visual_summary=visual_summary)
    prompt = build_system_prompt(setup, identity, dry_run=dry_run)
    return Stage0CompileResult(
        identity=identity,
        training_manifest=training,
        asset_manifest=assets,
        system_prompt=prompt,
    )


def write_stage0_artifacts(result: Stage0CompileResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "identity_matrix.json").write_text(
        json.dumps(result.identity.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "training_materials_manifest.json").write_text(
        json.dumps(result.training_manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "asset_manifest.json").write_text(
        json.dumps(result.asset_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "system_prompt.md").write_text(result.system_prompt, encoding="utf-8")
