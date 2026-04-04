from __future__ import annotations

import json
from pathlib import Path

from abunny_stage0_identity.models_input import PersonaSetup
from abunny_stage0_identity.pipeline import compile_stage0, write_stage0_artifacts
from pipeline_contracts.models import IdentityMatrix, TrainingMaterialsManifest


def test_compile_and_write_roundtrip(tmp_path: Path) -> None:
    setup = PersonaSetup.model_validate(
        {
            "display_name": "Z",
            "niche": "zine",
            "visual_style": {"palette": ["#000000"]},
        }
    )
    result = compile_stage0(setup, dry_run=True, matrix_id="im_pipeline_test")
    write_stage0_artifacts(result, tmp_path)

    im_raw = json.loads((tmp_path / "identity_matrix.json").read_text(encoding="utf-8"))
    IdentityMatrix.model_validate(im_raw)

    tm_raw = json.loads((tmp_path / "training_materials_manifest.json").read_text(encoding="utf-8"))
    tm = TrainingMaterialsManifest.model_validate(tm_raw)
    assert tm.matrix_id == "im_pipeline_test"
    kinds = {i.kind.value for i in tm.items}
    assert "style_ref" in kinds
    assert "transcript" in kinds

    am = json.loads((tmp_path / "asset_manifest.json").read_text(encoding="utf-8"))
    assert am["dry_run"] is True
    assert am["matrix_id"] == "im_pipeline_test"
    providers = {a["provider"] for a in am["assets"]}
    assert "higgsfield" in providers
    assert "elevenlabs" in providers
    assert "nano_banana" in providers

    md = (tmp_path / "system_prompt.md").read_text(encoding="utf-8")
    assert "im_pipeline_test" in md
    assert "# Creator identity" in md
