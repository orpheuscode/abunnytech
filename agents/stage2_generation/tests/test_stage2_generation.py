from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from abunny_stage2_generation.pipeline import run_stage2_generation

from pipeline_contracts.models import IdentityMatrix, VideoBlueprint
from pipeline_contracts.models.identity import AvatarPackRef, PersonaAxis, VoicePackRef
from pipeline_core.audit import AuditLogger
from pipeline_core.db import init_schema
from pipeline_core.repository import RunRepository
from pipeline_core.settings import Settings


class _StubRenderer:
    def render(self, blueprint: VideoBlueprint, output_path: Path, dry_run: bool) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"stub")
        return output_path


def test_run_stage2_generation_dry_run(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    repo = RunRepository(conn)
    audit = AuditLogger(conn)
    run_id = str(uuid.uuid4())
    repo.create_run(run_id)

    identity = IdentityMatrix(
        matrix_id="m1",
        display_name="T",
        niche="n",
        persona=PersonaAxis(tone="t", disclosure_line="D"),
        avatar=AvatarPackRef(avatar_id="a1"),
        voice=VoicePackRef(voice_id="v1"),
    )
    blueprint = VideoBlueprint(
        blueprint_id="b1",
        matrix_id="m1",
        title="T",
        hook="H",
        outline=["one", "two"],
        audio_id="snd1",
        duration_seconds_target=12,
    )
    repo.set_artifact(run_id, "identity_matrix", identity.model_dump(mode="json"))
    repo.set_artifact(run_id, "video_blueprint", blueprint.model_dump(mode="json"))

    settings = Settings(
        database_url="sqlite:///:memory:",
        dry_run=True,
        artifacts_dir=tmp_path / "art",
        disclosure_demo=True,
    )
    result = run_stage2_generation(
        run_id,
        repo,
        audit,
        settings,
        _StubRenderer(),
        blueprint=blueprint,
        identity=identity,
        carousel_slide_count=1,
        story_frame_count=0,
    )
    assert result.primary_package.run_id == run_id
    assert result.primary_package.blueprint_id == "b1"
    assert len(result.variant_packages) == 2
    assert (tmp_path / "art" / run_id / "stage2" / "elevenlabs_audio_request.json").is_file()
