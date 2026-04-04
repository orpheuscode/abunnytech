"""
Instagram platform adapter.

Live path:  Instagram Graph API via PlatformAPIProvider
Demo/test:  MockProvider (zero credentials)

API docs: https://developers.facebook.com/docs/instagram-api

Credential env vars:
  INSTAGRAM_ACCESS_TOKEN   — long-lived User access token
  INSTAGRAM_ACCOUNT_ID     — IG User ID (numeric)
"""
from __future__ import annotations

import os

from ..audit import AuditLogger
from ..providers.base import BrowserProvider
from ..providers.mock import MockProvider
from ..types import (
    AgentTask,
    AnalyticsData,
    AnalyticsFetchRequest,
    CommentReplyRequest,
    CommentReplyResult,
    DMRequest,
    DMResult,
    Platform,
    PlatformAPIRequest,
    PostContentRequest,
    PostContentResult,
    TrendingFetchRequest,
    TrendingItem,
)
from .base import PlatformAdapter


class InstagramAdapter(PlatformAdapter):

    def __init__(self, provider: BrowserProvider, audit: AuditLogger | None = None) -> None:
        super().__init__(provider, audit)
        self._account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")

    @property
    def platform(self) -> Platform:
        return Platform.INSTAGRAM

    async def post_content(self, request: PostContentRequest) -> PostContentResult:
        self._check_kill_switch()
        self._enforce_ai_disclosure(request)
        self._audit.log_request("instagram", "post_content", request.request_id, request.dry_run)

        if isinstance(self._provider, MockProvider):
            result = await self._provider.post_content(request)
            self._audit.log_result("instagram", "post_content", request.request_id, result.success, result.dry_run)
            return result

        if not self._account_id:
            raise RuntimeError("INSTAGRAM_ACCOUNT_ID env var is not set.")

        # Step 1: Create container
        caption = request.caption
        if request.hashtags:
            caption += "\n" + " ".join(f"#{h.lstrip('#')}" for h in request.hashtags)

        create_req = PlatformAPIRequest(
            platform=Platform.INSTAGRAM,
            method="POST",
            endpoint=f"/{self._account_id}/media",
            body={
                "video_url": request.media_url,  # must be publicly accessible
                "caption": caption,
                "media_type": "REELS",
            },
            dry_run=request.dry_run,
        )
        create_resp = await self._provider.call_platform_api(create_req)
        container_id = create_resp.data.get("id")

        # Step 2: Publish container
        publish_req = PlatformAPIRequest(
            platform=Platform.INSTAGRAM,
            method="POST",
            endpoint=f"/{self._account_id}/media_publish",
            body={"creation_id": container_id},
            dry_run=request.dry_run,
        )
        publish_resp = await self._provider.call_platform_api(publish_req)
        post_id = publish_resp.data.get("id")

        result = PostContentResult(
            request_id=request.request_id,
            platform=Platform.INSTAGRAM,
            success=bool(post_id),
            post_id=post_id,
            post_url=f"https://www.instagram.com/p/{post_id}/" if post_id else None,
            dry_run=request.dry_run,
        )
        self._audit.log_result("instagram", "post_content", request.request_id, result.success, result.dry_run)
        return result

    async def reply_to_comment(self, request: CommentReplyRequest) -> CommentReplyResult:
        self._check_kill_switch()
        self._audit.log_request("instagram", "reply_comment", request.request_id, request.dry_run)

        if isinstance(self._provider, MockProvider):
            result = await self._provider.reply_comment(request)
            self._audit.log_result("instagram", "reply_comment", request.request_id, result.success, result.dry_run)
            return result

        api_request = PlatformAPIRequest(
            platform=Platform.INSTAGRAM,
            method="POST",
            endpoint=f"/{request.comment_id}/replies",
            body={"message": request.reply_text},
            dry_run=request.dry_run,
        )
        api_response = await self._provider.call_platform_api(api_request)
        result = CommentReplyResult(
            request_id=request.request_id,
            platform=Platform.INSTAGRAM,
            success=api_response.status_code == 200,
            reply_id=api_response.data.get("id"),
            dry_run=request.dry_run,
        )
        self._audit.log_result("instagram", "reply_comment", request.request_id, result.success, result.dry_run)
        return result

    async def send_dm(self, request: DMRequest) -> DMResult:
        self._check_kill_switch()
        self._enforce_ai_disclosure(request)
        self._audit.log_request("instagram", "send_dm", request.request_id, request.dry_run)

        if isinstance(self._provider, MockProvider):
            result = await self._provider.send_dm(request)
            self._audit.log_result("instagram", "send_dm", request.request_id, result.success, result.dry_run)
            return result

        # Instagram Messaging API (requires instagram_manage_messages permission)
        api_request = PlatformAPIRequest(
            platform=Platform.INSTAGRAM,
            method="POST",
            endpoint="/me/messages",
            body={
                "recipient": {"id": request.recipient_id},
                "message": {"text": request.message},
            },
            dry_run=request.dry_run,
        )
        api_response = await self._provider.call_platform_api(api_request)
        result = DMResult(
            request_id=request.request_id,
            platform=Platform.INSTAGRAM,
            success=api_response.status_code == 200,
            message_id=api_response.data.get("message_id"),
            dry_run=request.dry_run,
        )
        self._audit.log_result("instagram", "send_dm", request.request_id, result.success, result.dry_run)
        return result

    async def fetch_analytics(self, request: AnalyticsFetchRequest) -> AnalyticsData:
        self._check_kill_switch()

        if isinstance(self._provider, MockProvider):
            return await self._provider.fetch_analytics(request)

        api_request = PlatformAPIRequest(
            platform=Platform.INSTAGRAM,
            method="GET",
            endpoint=f"/{request.post_id}/insights",
            params={
                "metric": "reach,impressions,likes,comments,shares,saved,follows",
                "period": "lifetime",
            },
        )
        api_response = await self._provider.call_platform_api(api_request)
        data = {item["name"]: item.get("values", [{}])[0].get("value", 0)
                for item in api_response.data.get("data", [])}
        return AnalyticsData(
            request_id=request.request_id,
            platform=Platform.INSTAGRAM,
            post_id=request.post_id,
            views=data.get("impressions", 0),
            likes=data.get("likes", 0),
            comments=data.get("comments", 0),
            shares=data.get("shares", 0),
            saves=data.get("saved", 0),
            follows_gained=data.get("follows", 0),
        )

    async def fetch_trending(self, request: TrendingFetchRequest) -> list[TrendingItem]:
        """Instagram has no public trending API; uses agent task as fallback."""
        self._check_kill_switch()

        if isinstance(self._provider, MockProvider):
            return await self._provider.fetch_trending(request)

        task = AgentTask(
            description=(
                f"Find the top {request.limit} trending Reels audio tracks on Instagram"
                + (f" related to: {', '.join(request.niche_tags)}" if request.niche_tags else "")
                + ". Return JSON list: audio_title, audio_author, usage_count."
            ),
            url="https://www.instagram.com/reels/audio/",
            dry_run=False,
        )
        result = await self._provider.run_agent_task(task)
        raw = result.output.get("trending", [])
        return [TrendingItem(platform=Platform.INSTAGRAM, **item) for item in raw[: request.limit]]
