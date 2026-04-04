"""
MockPlatformAdapter — in-memory adapter with no external dependencies.

All three operations return realistic-looking results after a 50 ms simulated
delay. Safe to use in tests and dry-run pipelines.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from browser_runtime.audit import get_audit
from browser_runtime.types import (
    CommentReplyRequest,
    CommentReplyResult,
    DMRequest,
    DMResult,
    PostContentRequest,
    PostContentResult,
)

from .base import PlatformAdapter

_MOCK_DELAY_SECONDS = 0.05  # 50 ms simulated network latency
_ADAPTER_NAME = "mock_adapter"


class MockPlatformAdapter(PlatformAdapter):
    """
    Concrete PlatformAdapter that never touches a real browser or platform.

    Intended for unit tests, integration smoke tests, and local dry runs.
    Always returns success=True with synthesised IDs and URLs.
    """

    async def _do_post_content(self, request: PostContentRequest) -> PostContentResult:
        audit = get_audit()
        audit.log_request(
            _ADAPTER_NAME,
            "post_content",
            request.request_id,
            self.dry_run,
            extra={"platform": request.platform.value},
        )
        await asyncio.sleep(_MOCK_DELAY_SECONDS)
        post_id = str(uuid.uuid4())
        result = PostContentResult(
            request_id=request.request_id,
            platform=request.platform,
            success=True,
            post_id=post_id,
            post_url=f"https://{request.platform.value}.com/p/{post_id}",
            posted_at=datetime.now(UTC),
            dry_run=True,
        )
        audit.log_result(
            _ADAPTER_NAME,
            "post_content",
            request.request_id,
            result.success,
            self.dry_run,
            extra={"post_id": result.post_id},
        )
        return result

    async def _do_reply_comment(self, request: CommentReplyRequest) -> CommentReplyResult:
        audit = get_audit()
        audit.log_request(
            _ADAPTER_NAME,
            "reply_comment",
            request.request_id,
            self.dry_run,
            extra={"platform": request.platform.value, "comment_id": request.comment_id},
        )
        await asyncio.sleep(_MOCK_DELAY_SECONDS)
        result = CommentReplyResult(
            request_id=request.request_id,
            platform=request.platform,
            success=True,
            reply_id=str(uuid.uuid4()),
            dry_run=True,
        )
        audit.log_result(
            _ADAPTER_NAME,
            "reply_comment",
            request.request_id,
            result.success,
            self.dry_run,
            extra={"reply_id": result.reply_id},
        )
        return result

    async def _do_send_dm(self, request: DMRequest) -> DMResult:
        audit = get_audit()
        audit.log_request(
            _ADAPTER_NAME,
            "send_dm",
            request.request_id,
            self.dry_run,
            extra={"platform": request.platform.value, "recipient_id": request.recipient_id},
        )
        await asyncio.sleep(_MOCK_DELAY_SECONDS)
        result = DMResult(
            request_id=request.request_id,
            platform=request.platform,
            success=True,
            message_id=str(uuid.uuid4()),
            dry_run=True,
        )
        audit.log_result(
            _ADAPTER_NAME,
            "send_dm",
            request.request_id,
            result.success,
            self.dry_run,
            extra={"message_id": result.message_id},
        )
        return result
