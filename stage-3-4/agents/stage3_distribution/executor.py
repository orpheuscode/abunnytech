"""
PostingExecutor — executes ScheduledPosts via a PlatformAdapter.

This is the thin orchestration layer between the scheduler and the adapter.
It builds the typed requests, enforces the ai_disclosure rule, records
DistributionRecords, and logs everything to audit.
"""
from __future__ import annotations

from datetime import UTC, datetime

from browser_runtime.audit import get_audit
from browser_runtime.types import (
    CommentReplyRequest,
    CommentReplyResult,
    DMRequest,
    DMResult,
    PostContentRequest,
)
from browser_runtime.types import (
    Platform as BrowserPlatform,
)

from .adapters.base import PlatformAdapter
from .contracts import (
    DistributionRecord,
    DistributionStatus,
    IdentityMatrix,
    Platform,
)
from .scheduler import ScheduledPost

_EXECUTOR_NAME = "posting_executor"


class PostingExecutor:
    """
    Executes ScheduledPosts and wraps results in DistributionRecords.

    Always appends ai_disclosure_footer to captions and always sets
    ai_disclosure=True on DMs — these are non-negotiable operating rules.
    """

    def __init__(
        self,
        adapter: PlatformAdapter,
        dry_run: bool = True,
    ) -> None:
        self._adapter = adapter
        self._dry_run = dry_run

    # ------------------------------------------------------------------
    # Post content
    # ------------------------------------------------------------------

    async def execute_post(
        self,
        scheduled_post: ScheduledPost,
        identity: IdentityMatrix,
    ) -> DistributionRecord:
        audit = get_audit()
        package = scheduled_post.package

        # Build the full caption with mandatory disclosure footer
        footer = identity.ai_disclosure_footer.format(persona_name=identity.persona_name)
        full_caption = f"{package.caption}\n\n{footer}"

        request = PostContentRequest(
            platform=BrowserPlatform(scheduled_post.platform.value),
            caption=full_caption,
            hashtags=package.hashtags,
            media_path=package.media_path,
            media_url=package.media_url,
            scheduled_at=scheduled_post.scheduled_at,
            dry_run=self._dry_run,
            ai_disclosure=True,
        )

        audit.log_request(
            _EXECUTOR_NAME,
            "execute_post",
            request.request_id,
            self._dry_run,
            extra={
                "platform": scheduled_post.platform.value,
                "package_id": package.package_id,
                "post_id": scheduled_post.post_id,
            },
        )

        result = await self._adapter.post_content(request)

        if self._dry_run or result.dry_run:
            status = DistributionStatus.DRY_RUN
        elif result.success:
            status = DistributionStatus.POSTED
        else:
            status = DistributionStatus.FAILED

        record = DistributionRecord(
            package_id=package.package_id,
            identity_id=identity.identity_id,
            platform=scheduled_post.platform,
            post_id=result.post_id,
            post_url=result.post_url,
            status=status,
            caption_used=full_caption,
            hashtags_used=package.hashtags,
            posted_at=result.posted_at or (datetime.now(UTC) if result.success else None),
            error=result.error,
            dry_run=self._dry_run,
            provider_used=self._adapter.provider.provider_type.value,
        )

        audit.log_result(
            _EXECUTOR_NAME,
            "execute_post",
            request.request_id,
            result.success,
            self._dry_run,
            extra={
                "record_id": record.record_id,
                "status": status.value,
                "error": result.error,
            },
        )

        return record

    # ------------------------------------------------------------------
    # Comment reply
    # ------------------------------------------------------------------

    async def execute_comment_reply(
        self,
        platform: Platform,
        post_id: str,
        comment_id: str,
        reply_text: str,
    ) -> CommentReplyResult:
        audit = get_audit()
        request = CommentReplyRequest(
            platform=BrowserPlatform(platform.value),
            post_id=post_id,
            comment_id=comment_id,
            reply_text=reply_text,
            dry_run=self._dry_run,
        )
        audit.log_request(
            _EXECUTOR_NAME,
            "execute_comment_reply",
            request.request_id,
            self._dry_run,
            extra={"platform": platform.value, "post_id": post_id, "comment_id": comment_id},
        )
        result = await self._adapter.reply_comment(request)
        audit.log_result(
            _EXECUTOR_NAME,
            "execute_comment_reply",
            request.request_id,
            result.success,
            self._dry_run,
            extra={"reply_id": result.reply_id, "error": result.error},
        )
        return result

    # ------------------------------------------------------------------
    # DM
    # ------------------------------------------------------------------

    async def execute_dm(
        self,
        platform: Platform,
        recipient_id: str,
        message: str,
    ) -> DMResult:
        audit = get_audit()
        request = DMRequest(
            platform=BrowserPlatform(platform.value),
            recipient_id=recipient_id,
            message=message,
            ai_disclosure=True,
            dry_run=self._dry_run,
        )
        audit.log_request(
            _EXECUTOR_NAME,
            "execute_dm",
            request.request_id,
            self._dry_run,
            extra={"platform": platform.value, "recipient_id": recipient_id},
        )
        result = await self._adapter.send_dm(request)
        audit.log_result(
            _EXECUTOR_NAME,
            "execute_dm",
            request.request_id,
            result.success,
            self._dry_run,
            extra={"message_id": result.message_id, "error": result.error},
        )
        return result
