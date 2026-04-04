"""Tests for BrowserSession / InMemorySession / SessionManager."""
from __future__ import annotations

import pytest

from browser_runtime.config import BrowserRuntimeSettings, KillSwitchConfig, override_settings
from browser_runtime.session import InMemorySession, KillSwitchTriggered


class TestInMemorySession:
    async def test_create_tab(self, session):
        tab = await session.create_tab("https://example.com")
        assert tab.tab_id
        assert tab.url == "https://example.com"

    async def test_list_tabs(self, session):
        await session.create_tab("https://a.com")
        await session.create_tab("https://b.com")
        tabs = await session.list_tabs()
        assert len(tabs) == 2

    async def test_close_tab(self, session):
        tab = await session.create_tab("https://x.com")
        await session.close_tab(tab.tab_id)
        tabs = await session.list_tabs()
        assert len(tabs) == 0

    async def test_close_all(self, session):
        await session.create_tab()
        await session.create_tab()
        await session.close_all()
        assert await session.list_tabs() == []

    async def test_save_and_restore_state(self, session):
        session.inject_cookies({"session_id": "abc123", "auth": "token_xyz"})
        state = await session.save_state()

        new_session = InMemorySession(platform="tiktok", dry_run=True)
        await new_session.restore_state(state)
        restored_state = await new_session.save_state()
        assert restored_state.cookies == {"session_id": "abc123", "auth": "token_xyz"}

    async def test_tab_navigate(self, session):
        tab = await session.create_tab()
        ok = await tab.navigate("https://tiktok.com")
        assert ok
        assert tab.url == "https://tiktok.com"
        content = await tab.get_content()
        assert "tiktok.com" in content

    async def test_tab_screenshot_returns_png(self, session):
        tab = await session.create_tab()
        png = await tab.screenshot()
        assert png[:4] == b"\x89PNG"

    async def test_kill_switch_blocks_create_tab(self):
        settings = BrowserRuntimeSettings(
            dry_run=True,
            global_kill_switch=KillSwitchConfig(enabled=True, reason="test stop"),
        )
        override_settings(settings)
        s = InMemorySession(dry_run=True)
        with pytest.raises(KillSwitchTriggered, match="test stop"):
            await s.create_tab()

    async def test_platform_kill_switch_blocks_create_tab(self):
        from browser_runtime.config import PlatformConfig
        settings = BrowserRuntimeSettings(
            dry_run=True,
            tiktok=PlatformConfig(kill_switch=KillSwitchConfig(enabled=True, reason="tiktok stopped")),
        )
        override_settings(settings)
        s = InMemorySession(platform="tiktok", dry_run=True)
        with pytest.raises(KillSwitchTriggered, match="tiktok stopped"):
            await s.create_tab()


class TestSessionManager:
    async def test_create_and_retrieve(self, session_manager):
        s = session_manager.create(platform="instagram", dry_run=True)
        retrieved = session_manager.get(s.session_id)
        assert retrieved is s

    async def test_active_count(self, session_manager):
        session_manager.create(dry_run=True)
        session_manager.create(dry_run=True)
        assert session_manager.active_count() == 2

    async def test_close_session(self, session_manager):
        s = session_manager.create(dry_run=True)
        await session_manager.close_session(s.session_id)
        assert session_manager.get(s.session_id) is None
        assert session_manager.active_count() == 0

    async def test_close_all(self, session_manager):
        session_manager.create(dry_run=True)
        session_manager.create(dry_run=True)
        await session_manager.close_all()
        assert session_manager.active_count() == 0

    async def test_get_nonexistent_returns_none(self, session_manager):
        assert session_manager.get("no-such-id") is None
