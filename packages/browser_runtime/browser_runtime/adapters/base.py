"""
PlatformAdapter abstract base class.

An adapter wraps a BrowserProvider with platform-specific knowledge:
  - which endpoints to call
  - how to format payloads
  - what retry/rate-limit config to apply
  - how to enforce AI disclosure requirements

Stage code only imports adapters, never providers directly.

Usage:
    provider = get_provider("mock", dry_run=True)
    adapter = TikTokAdapter(provider)
    result = await adapter.post_content(PostContentRequest(...))
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..audit import AuditLogger, get_audit
from ..providers.base import BrowserProvider
from ..types import (
    AnalyticsData,
    AnalyticsFetchRequest,
    CommentReplyRequest,
    CommentReplyResult,
    DMRequest,
    DMResult,
    Platform,
    PostContentRequest,
    PostContentResult,
    TrendingFetchRequest,
    TrendingItem,
)


class PlatformAdapter(ABC):
    """
    Platform-specific operation interface.

    All write operations (post, reply, dm) must:
      1. Honour dry_run — never make real writes when True.
      2. Enforce ai_disclosure — must not be disabled per operating rules.
      3. Log every operation to the audit logger.
      4. Apply the platform's kill switch before any network call.
    """

    def __init__(
        self,
        provider: BrowserProvider,
        audit: AuditLogger | None = None,
    ) -> None:
        self._provider = provider
        self._audit = audit or get_audit()

    @property
    @abstractmethod
    def platform(self) -> Platform: ...

    @abstractmethod
    async def post_content(self, request: PostContentRequest) -> PostContentResult:
        """Publish a video/image/reel to this platform."""

    @abstractmethod
    async def reply_to_comment(self, request: CommentReplyRequest) -> CommentReplyResult:
        """Post a reply to an existing comment."""

    @abstractmethod
    async def send_dm(self, request: DMRequest) -> DMResult:
        """Send a direct message to a user."""

    @abstractmethod
    async def fetch_analytics(self, request: AnalyticsFetchRequest) -> AnalyticsData:
        """Retrieve performance metrics for a post or account."""

    @abstractmethod
    async def fetch_trending(self, request: TrendingFetchRequest) -> list[TrendingItem]:
        """Return currently trending audio/topics on this platform."""

    # ------------------------------------------------------------------
    # Shared guard — subclasses call this at the top of each method
    # ------------------------------------------------------------------

    def _check_kill_switch(self) -> None:
        from ..config import get_settings
        from ..session import KillSwitchTriggered
        settings = get_settings()
        if settings.global_kill_switch.enabled:
            raise KillSwitchTriggered(settings.global_kill_switch.reason)
        pc = settings.platform_config(self.platform.value)
        if pc.kill_switch.enabled:
            raise KillSwitchTriggered(pc.kill_switch.reason)

    def _enforce_ai_disclosure(self, request: PostContentRequest | DMRequest) -> None:
        """Raise if caller tried to disable AI disclosure — non-negotiable per operating rules."""
        if not request.ai_disclosure:
            raise ValueError(
                "ai_disclosure must be True. "
                "Disabling AI disclosure is not permitted per operating rules."
            )
