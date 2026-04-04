"""
Browser session abstraction.

BrowserSession manages the lifecycle of a browser context: authentication state,
tab inventory, session persistence, and audit hooks.  Concrete implementations
live in provider packages; stages only depend on this interface.

Quick start:
    from browser_runtime.session import InMemorySession, SessionManager

    mgr = SessionManager()
    session = mgr.create("instagram", dry_run=True)
    state = await session.save_state()
    await session.restore_state(state)
    await session.close()
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from .audit import get_audit
from .types import SessionState, TabInfo

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class KillSwitchTriggered(RuntimeError):
    """Raised when the global or per-platform kill switch is active."""


class SessionError(RuntimeError):
    """General browser session error."""


# ---------------------------------------------------------------------------
# Abstract interfaces
# ---------------------------------------------------------------------------


class Tab(ABC):
    """Abstraction over a single browser tab."""

    @property
    @abstractmethod
    def tab_id(self) -> str: ...

    @property
    @abstractmethod
    def url(self) -> str: ...

    @abstractmethod
    async def navigate(self, url: str) -> bool:
        """Navigate to url. Returns True on success."""

    @abstractmethod
    async def get_content(self) -> str:
        """Return the current page's text content."""

    @abstractmethod
    async def screenshot(self) -> bytes:
        """Return PNG bytes of the current viewport."""

    @abstractmethod
    async def close(self) -> None: ...


class BrowserSession(ABC):
    """
    Abstract browser session.

    A session holds authentication state (cookies, local storage) for a single
    platform/account.  Tabs are opened within a session.

    All mutating operations check the kill switch before proceeding.
    """

    def __init__(
        self,
        session_id: str | None = None,
        platform: str | None = None,
        dry_run: bool = True,
    ) -> None:
        self._session_id = session_id or str(uuid.uuid4())
        self._platform = platform
        self._dry_run = dry_run
        self._created_at = datetime.now(UTC)
        self._audit = get_audit()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @property
    def platform(self) -> str | None:
        return self._platform

    # -- Tab management --

    @abstractmethod
    async def create_tab(self, url: str = "") -> Tab:
        """Open a new tab, optionally navigating to url."""

    @abstractmethod
    async def close_tab(self, tab_id: str) -> None: ...

    @abstractmethod
    async def list_tabs(self) -> list[TabInfo]: ...

    @abstractmethod
    async def close_all(self) -> None:
        """Close all tabs and release browser resources."""

    # -- State persistence --

    @abstractmethod
    async def save_state(self) -> SessionState:
        """Snapshot current cookies/storage for later restoration."""

    @abstractmethod
    async def restore_state(self, state: SessionState) -> None:
        """Restore a previously saved session state."""

    # -- Kill switch --

    def _check_kill_switch(self) -> None:
        """Raise KillSwitchTriggered if globally or platform-level disabled."""
        from .config import get_settings
        settings = get_settings()
        if settings.global_kill_switch.enabled:
            raise KillSwitchTriggered(settings.global_kill_switch.reason)
        if self._platform:
            pc = settings.platform_config(self._platform)
            if pc.kill_switch.enabled:
                raise KillSwitchTriggered(pc.kill_switch.reason)

    async def close(self) -> None:
        """Alias for close_all() — preferred teardown method."""
        await self.close_all()


# ---------------------------------------------------------------------------
# InMemorySession — lightweight implementation for mocks and tests
# ---------------------------------------------------------------------------


class InMemoryTab(Tab):
    """Minimal in-memory tab. Content and screenshots are stubs."""

    def __init__(self, tab_id: str, url: str = "") -> None:
        self._tab_id = tab_id
        self._url = url
        self._content: str = ""

    @property
    def tab_id(self) -> str:
        return self._tab_id

    @property
    def url(self) -> str:
        return self._url

    async def navigate(self, url: str) -> bool:
        self._url = url
        self._content = f"[mock page: {url}]"
        return True

    async def get_content(self) -> str:
        return self._content or f"[mock page: {self._url}]"

    async def screenshot(self) -> bytes:
        # 1x1 white PNG — keeps tests fast without pillow
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    async def close(self) -> None:
        pass


class InMemorySession(BrowserSession):
    """
    Fully in-memory session — no browser process required.

    Used by MockProvider and unit tests.  All operations are logged to audit.
    """

    def __init__(
        self,
        session_id: str | None = None,
        platform: str | None = None,
        dry_run: bool = True,
    ) -> None:
        super().__init__(session_id, platform, dry_run)
        self._tabs: dict[str, InMemoryTab] = {}
        self._cookies: dict[str, Any] = {}
        self._local_storage: dict[str, Any] = {}

    async def create_tab(self, url: str = "") -> Tab:
        self._check_kill_switch()
        tab = InMemoryTab(tab_id=str(uuid.uuid4()), url=url)
        self._tabs[tab.tab_id] = tab
        self._audit.log(
            "session.create_tab",
            {"session_id": self._session_id, "tab_id": tab.tab_id, "url": url},
        )
        return tab

    async def close_tab(self, tab_id: str) -> None:
        self._tabs.pop(tab_id, None)
        self._audit.log("session.close_tab", {"session_id": self._session_id, "tab_id": tab_id})

    async def list_tabs(self) -> list[TabInfo]:
        return [TabInfo(tab_id=t.tab_id, url=t.url) for t in self._tabs.values()]

    async def close_all(self) -> None:
        self._tabs.clear()
        self._audit.log("session.close_all", {"session_id": self._session_id})

    async def save_state(self) -> SessionState:
        from .types import Platform
        p = None
        if self._platform:
            try:
                p = Platform(self._platform)
            except ValueError:
                pass
        state = SessionState(
            session_id=self._session_id,
            platform=p,
            cookies=dict(self._cookies),
            local_storage=dict(self._local_storage),
        )
        self._audit.log("session.save_state", {"session_id": self._session_id})
        return state

    async def restore_state(self, state: SessionState) -> None:
        self._cookies = dict(state.cookies)
        self._local_storage = dict(state.local_storage)
        self._audit.log(
            "session.restore_state",
            {"session_id": self._session_id, "restored_from": state.session_id},
        )

    def inject_cookies(self, cookies: dict[str, Any]) -> None:
        """Test helper: inject fake cookies to simulate logged-in state."""
        self._cookies.update(cookies)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """
    Creates and tracks browser sessions.

    Usage:
        mgr = SessionManager()
        session = mgr.create("tiktok", dry_run=True)
        # ... use session ...
        await mgr.close_all()
    """

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}

    def create(
        self,
        platform: str | None = None,
        dry_run: bool = True,
        session_class: type[BrowserSession] = InMemorySession,
        **kwargs: Any,
    ) -> BrowserSession:
        session = session_class(platform=platform, dry_run=dry_run, **kwargs)
        self._sessions[session.session_id] = session
        get_audit().log(
            "session_manager.create",
            {"session_id": session.session_id, "platform": platform, "dry_run": dry_run},
        )
        return session

    def get(self, session_id: str) -> BrowserSession | None:
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            await session.close()

    async def close_all(self) -> None:
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()

    def active_count(self) -> int:
        return len(self._sessions)
