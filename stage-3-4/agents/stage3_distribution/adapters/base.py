"""
PlatformAdapter abstract base class.

Wraps a BrowserProvider and exposes the three social-platform operations used
by Stage 3: posting content, replying to comments, and sending DMs.

Dry-run mode returns simulated success results without calling the provider.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from browser_runtime.audit import get_audit
from browser_runtime.providers.base import BrowserProvider
from browser_runtime.session import KillSwitchTriggered
from browser_runtime.types import (
    CommentReplyRequest,
    CommentReplyResult,
    DMRequest,
    DMResult,
    PostContentRequest,
    PostContentResult,
)

_ADAPTER_NAME = "platform_adapter"


class PlatformAdapter(ABC):
    """
    Abstract adapter that stages interact with to publish content.

    Subclasses implement the three abstract methods; this base handles
    audit logging, dry-run short-circuiting, and kill-switch interception.
    """

    def __init__(self, provider: BrowserProvider, dry_run: bool = True) -> None:
        self._provider = provider
        self._dry_run = dry_run

    @property
    def provider(self) -> BrowserProvider:
        return self._provider

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    # ------------------------------------------------------------------
    # Abstract methods — subclasses supply the actual logic
    # ------------------------------------------------------------------

    @abstractmethod
    async def _do_post_content(self, request: PostContentRequest) -> PostContentResult: ...

    @abstractmethod
    async def _do_reply_comment(self, request: CommentReplyRequest) -> CommentReplyResult: ...

    @abstractmethod
    async def _do_send_dm(self, request: DMRequest) -> DMResult: ...

    # ------------------------------------------------------------------
    # Public API — handles logging, dry-run, and kill-switch for free
    # ------------------------------------------------------------------

    async def post_content(self, request: PostContentRequest) -> PostContentResult:
        audit = get_audit()
        audit.log_request(
            _ADAPTER_NAME,
            "post_content",
            request.request_id,
            self._dry_run,
            extra={"platform": request.platform.value},
        )
        if self._dry_run:
            result = PostContentResult(
                request_id=request.request_id,
                platform=request.platform,
                success=True,
                dry_run=True,
            )
            audit.log_result(_ADAPTER_NAME, "post_content", request.request_id, True, True)
            return result
        try:
            result = await self._do_post_content(request)
        except KillSwitchTriggered as exc:
            result = PostContentResult(
                request_id=request.request_id,
                platform=request.platform,
                success=False,
                error=f"kill_switch: {exc}",
                dry_run=self._dry_run,
            )
        audit.log_result(
            _ADAPTER_NAME,
            "post_content",
            request.request_id,
            result.success,
            self._dry_run,
            extra={"error": result.error},
        )
        return result

    async def reply_comment(self, request: CommentReplyRequest) -> CommentReplyResult:
        audit = get_audit()
        audit.log_request(
            _ADAPTER_NAME,
            "reply_comment",
            request.request_id,
            self._dry_run,
            extra={"platform": request.platform.value, "comment_id": request.comment_id},
        )
        if self._dry_run:
            result = CommentReplyResult(
                request_id=request.request_id,
                platform=request.platform,
                success=True,
                dry_run=True,
            )
            audit.log_result(_ADAPTER_NAME, "reply_comment", request.request_id, True, True)
            return result
        try:
            result = await self._do_reply_comment(request)
        except KillSwitchTriggered as exc:
            result = CommentReplyResult(
                request_id=request.request_id,
                platform=request.platform,
                success=False,
                error=f"kill_switch: {exc}",
                dry_run=self._dry_run,
            )
        audit.log_result(
            _ADAPTER_NAME,
            "reply_comment",
            request.request_id,
            result.success,
            self._dry_run,
            extra={"error": result.error},
        )
        return result

    async def send_dm(self, request: DMRequest) -> DMResult:
        audit = get_audit()
        audit.log_request(
            _ADAPTER_NAME,
            "send_dm",
            request.request_id,
            self._dry_run,
            extra={"platform": request.platform.value, "recipient_id": request.recipient_id},
        )
        if self._dry_run:
            result = DMResult(
                request_id=request.request_id,
                platform=request.platform,
                success=True,
                dry_run=True,
            )
            audit.log_result(_ADAPTER_NAME, "send_dm", request.request_id, True, True)
            return result
        try:
            result = await self._do_send_dm(request)
        except KillSwitchTriggered as exc:
            result = DMResult(
                request_id=request.request_id,
                platform=request.platform,
                success=False,
                error=f"kill_switch: {exc}",
                dry_run=self._dry_run,
            )
        audit.log_result(
            _ADAPTER_NAME,
            "send_dm",
            request.request_id,
            result.success,
            self._dry_run,
            extra={"error": result.error},
        )
        return result
