from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure API src is importable when tests run from repo root without editable install
API_SRC = ROOT / "apps" / "api" / "src"
if API_SRC.exists() and str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))


@pytest.fixture
def temp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "test.db"
    art = tmp_path / "artifacts"
    monkeypatch.setenv("PIPELINE_DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("PIPELINE_ARTIFACTS_DIR", str(art))
    monkeypatch.setenv("PIPELINE_DRY_RUN", "false")
    from pipeline_core.settings import get_settings

    get_settings.cache_clear()
    return tmp_path


@pytest.fixture
def api_client(temp_env: Path) -> Generator:
    from fastapi.testclient import TestClient

    from apps.api.main import app

    with TestClient(app) as c:
        yield c
