"""Shared pytest fixtures for browser_runtime tests."""
from __future__ import annotations

import pytest

from browser_runtime.audit import AuditLogger, override_audit
from browser_runtime.config import BrowserRuntimeSettings, override_settings
from browser_runtime.providers.mock import MockProvider
from browser_runtime.session import InMemorySession, SessionManager


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    """Each test gets a fresh settings singleton with dry_run=True and mock provider."""
    settings = BrowserRuntimeSettings(
        dry_run=True,
        provider="mock",
        audit_log_path=str(tmp_path / "test_audit.jsonl"),
    )
    override_settings(settings)
    yield settings
    # Reset to None so next test re-creates
    override_settings(None)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _isolated_audit(tmp_path, _isolated_settings):
    """Each test gets a fresh AuditLogger writing to a temp file."""
    audit = AuditLogger(str(tmp_path / "test_audit.jsonl"))
    override_audit(audit)
    yield audit
    override_audit(None)  # type: ignore[arg-type]


@pytest.fixture
def mock_provider():
    return MockProvider(dry_run=True)


@pytest.fixture
def live_mock_provider():
    """Mock provider with dry_run=False — simulates 'live' writes without real network."""
    return MockProvider(dry_run=False)


@pytest.fixture
def session():
    return InMemorySession(platform="tiktok", dry_run=True)


@pytest.fixture
def session_manager():
    return SessionManager()
