from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pipeline_contracts.models import IdentityMatrix
from pipeline_contracts.models.identity import AvatarPackRef, PersonaAxis, VoicePackRef
from pipeline_core.audit import AuditLogger
from pipeline_core.db import init_schema
from pipeline_core.repository import RunRepository
from pipeline_core.settings import Settings
from pipeline_stage1_discover import MockDiscoveryProvider, run_stage1


@pytest.fixture
def sqlite_repo(tmp_path: Path) -> tuple[str, RunRepository, AuditLogger, Settings]:
    db = tmp_path / "s.db"
    conn = sqlite3.connect(str(db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    repo = RunRepository(conn)
    audit = AuditLogger(conn)
    settings = Settings(
        database_url=f"sqlite:///{db}",
        artifacts_dir=tmp_path / "a",
        dry_run=False,
    )
    run_id = repo.create_run()
    im = IdentityMatrix(
        matrix_id="mx",
        display_name="D",
        niche="cooking",
        persona=PersonaAxis(tone="warm"),
        avatar=AvatarPackRef(avatar_id="a"),
        voice=VoicePackRef(voice_id="v"),
    )
    repo.set_artifact(run_id, "identity_matrix", im.model_dump(mode="json"))
    return run_id, repo, audit, settings


def test_stage1_blueprint(sqlite_repo: tuple) -> None:
    run_id, repo, audit, settings = sqlite_repo
    bp = run_stage1(run_id, repo, audit, settings, MockDiscoveryProvider())
    assert bp.matrix_id == "mx"
    assert bp.audio_id
    stored = repo.get_artifact(run_id, "video_blueprint")
    assert stored and stored["blueprint_id"] == bp.blueprint_id
