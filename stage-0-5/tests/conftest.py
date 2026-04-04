"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Ensure tests use a temp DB and dry-run mode."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("FEATURE_STAGE5_MONETIZE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")

    from packages.shared.config import get_settings
    get_settings.cache_clear()

    import packages.shared.db as db_mod
    db_mod._async_engine = None
    db_mod._async_session_factory = None

    yield

    get_settings.cache_clear()
    db_mod._async_engine = None
    db_mod._async_session_factory = None


@pytest.fixture
async def registry(tmp_path):
    """Fixture for packages.state tests: provides a RepositoryRegistry backed by a temp SQLite DB."""
    from packages.state.registry import RepositoryRegistry
    from packages.state.sqlite import Database

    db_path = tmp_path / "state_test.db"
    db = Database(str(db_path))
    await db.connect()
    reg = RepositoryRegistry(db)
    for repo in reg.all_repos().values():
        await repo._ensure_table()
    yield reg
    await db.disconnect()
