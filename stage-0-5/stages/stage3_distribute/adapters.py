from __future__ import annotations

from typing import Protocol

import structlog

from packages.contracts.base import Platform, new_id
from packages.contracts.content import ContentPackage
from packages.contracts.distribution import DistributionRecord, DistributionStatus
from packages.contracts.identity import IdentityMatrix

log = structlog.get_logger(__name__)


class PlatformPosterAdapter(Protocol):
    async def post(self, content_package: ContentPackage, platform: Platform) -> DistributionRecord:
        """Publish a content package to the given platform."""


class CommentReplyAdapter(Protocol):
    async def generate_reply(self, comment_text: str, identity: IdentityMatrix) -> str:
        """Draft a reply that matches the creator persona."""


class BrowserAutomationAdapter(Protocol):
    async def execute_post(self, url: str, content: str) -> bool:
        """Drive browser automation to submit a post at ``url`` with ``content``."""


class MockPlatformPoster:
    """Simulates a successful post and returns a plausible ``DistributionRecord``."""

    async def post(self, content_package: ContentPackage, platform: Platform) -> DistributionRecord:
        fake_post_id = str(new_id())[:8]
        post_url = f"https://{platform.value}.example.com/p/{fake_post_id}"
        log.info(
            "mock_platform_post",
            platform=platform.value,
            content_package_id=str(content_package.id),
            simulated_post_url=post_url,
        )
        return DistributionRecord(
            content_package_id=str(content_package.id),
            identity_id=content_package.identity_id,
            platform=platform,
            post_url=post_url,
            post_id=f"mock_{platform.value}_{fake_post_id}",
            status=DistributionStatus.POSTED,
            dry_run=False,
        )


class MockCommentReply:
    """Template-based replies aligned with archetype and tone (no LLM)."""

    async def generate_reply(self, comment_text: str, identity: IdentityMatrix) -> str:
        tone = identity.guidelines.tone or "friendly"
        archetype = identity.archetype.value
        opener = {
            "educator": "Really appreciate you taking the time to comment",
            "entertainer": "Haha, love the energy here",
            "motivator": "Thanks for the boost",
            "reviewer": "Great point — I hear you",
            "storyteller": "That means a lot — stories land when people connect",
        }.get(archetype, "Thanks so much")
        body = (
            f"{opener}! As {identity.name}, I try to keep things {tone}. "
            f"Re: \"{comment_text[:120]}{'…' if len(comment_text) > 120 else ''}\" — "
            f"happy to share more if useful."
        )
        log.debug("mock_comment_reply_generated", archetype=archetype, tone=tone)
        return body


class MockBrowserAutomation:
    """Logs the automation plan without touching a real browser."""

    async def execute_post(self, url: str, content: str) -> bool:
        preview = content if len(content) <= 280 else f"{content[:280]}…"
        log.info(
            "mock_browser_automation_would_execute",
            url=url,
            content_preview=preview,
            content_chars=len(content),
        )
        return True


class PlaywrightBrowserAutomation:
    """TODO: Wire Playwright page navigation, auth/session cookies, and upload flows."""

    async def execute_post(self, url: str, content: str) -> bool:
        # TODO: Launch browser (headless configurable), open ``url``, fill caption/body from ``content``
        # TODO: Attach media from ContentPackage assets when integrated with the service layer
        # TODO: Handle platform-specific selectors (TikTok / IG / YouTube / X)
        log.warning("playwright_execute_post_not_implemented", url=url, content_len=len(content))
        return False
