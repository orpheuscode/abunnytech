"""
TikTok platform adapter.

Live path:  TikTok Content Posting API (v2) via PlatformAPIProvider
            OR browser-use agent via BrowserUseProvider
Demo/test:  MockProvider (zero credentials)

TikTok API docs: https://developers.tiktok.com/doc/content-posting-api-get-started

Credential env vars:
  TIKTOK_ACCESS_TOKEN   — OAuth2 access token
  TIKTOK_OPEN_ID        — Creator open_id (returned at OAuth time)
"""
from __future__ import annotations

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


class TikTokAdapter(PlatformAdapter):
    """
    TikTok operations via the configured provider.

    When provider is MockProvider the call never leaves the process.
    When provider is PlatformAPIProvider the official TikTok API is used.
    When provider is BrowserUseProvider the agent navigates TikTok.com.
    """

    def __init__(self, provider: BrowserProvider, audit: AuditLogger | None = None) -> None:
        super().__init__(provider, audit)

    @property
    def platform(self) -> Platform:
        return Platform.TIKTOK

    async def post_content(self, request: PostContentRequest) -> PostContentResult:
        self._check_kill_switch()
        self._enforce_ai_disclosure(request)
        self._audit.log_request("tiktok", "post_content", request.request_id, request.dry_run)

        if isinstance(self._provider, MockProvider):
            result = await self._provider.post_content(request)
            self._audit.log_result("tiktok", "post_content", request.request_id, result.success, result.dry_run)
            return result

        # Official API path (Content Posting API v2)
        # TODO: upload video file first → get video_id, then publish
        # Step 1: init upload
        # POST /v2/post/publish/video/init/
        # Step 2: upload file chunks to upload_url
        # Step 3: confirm publish
        # POST /v2/post/publish/video/complete/
        api_request = PlatformAPIRequest(
            platform=Platform.TIKTOK,
            method="POST",
            endpoint="/v2/post/publish/video/init/",
            body={
                "post_info": {
                    "title": request.caption[:150],  # TikTok max caption = 150 chars
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    # "video_size": <file_size_bytes>  — TODO: compute from media_path
                },
            },
            dry_run=request.dry_run,
        )
        api_response = await self._provider.call_platform_api(api_request)

        result = PostContentResult(
            request_id=request.request_id,
            platform=Platform.TIKTOK,
            success=api_response.status_code == 200,
            post_id=api_response.data.get("publish_id"),
            error=api_response.error,
            dry_run=request.dry_run,
        )
        self._audit.log_result("tiktok", "post_content", request.request_id, result.success, result.dry_run)
        return result

    async def reply_to_comment(self, request: CommentReplyRequest) -> CommentReplyResult:
        self._check_kill_switch()
        self._audit.log_request("tiktok", "reply_comment", request.request_id, request.dry_run)

        if isinstance(self._provider, MockProvider):
            result = await self._provider.reply_comment(request)
            self._audit.log_result("tiktok", "reply_comment", request.request_id, result.success, result.dry_run)
            return result

        # TODO: TikTok does not expose a public comment reply API as of 2024.
        # Fall back to BrowserUseProvider agent task.
        task = AgentTask(
            description=(
                f"On TikTok, reply to comment ID {request.comment_id} "
                f"on post {request.post_id} with: {request.reply_text}"
            ),
            dry_run=request.dry_run,
        )
        agent_result = await self._provider.run_agent_task(task)
        result = CommentReplyResult(
            request_id=request.request_id,
            platform=Platform.TIKTOK,
            success=agent_result.success,
            reply_id=agent_result.output.get("reply_id"),
            error=agent_result.error,
            dry_run=request.dry_run,
        )
        self._audit.log_result("tiktok", "reply_comment", request.request_id, result.success, result.dry_run)
        return result

    async def send_dm(self, request: DMRequest) -> DMResult:
        self._check_kill_switch()
        self._enforce_ai_disclosure(request)
        self._audit.log_request("tiktok", "send_dm", request.request_id, request.dry_run)

        if isinstance(self._provider, MockProvider):
            result = await self._provider.send_dm(request)
            self._audit.log_result("tiktok", "send_dm", request.request_id, result.success, result.dry_run)
            return result

        # TODO: TikTok DM API requires special partner access.
        # For authorized sandbox accounts only.
        raise NotImplementedError(
            "TikTok DM API requires partner-level access. "
            "Use MockProvider for testing or obtain partner credentials."
        )

    async def fetch_analytics(self, request: AnalyticsFetchRequest) -> AnalyticsData:
        self._check_kill_switch()

        if isinstance(self._provider, MockProvider):
            return await self._provider.fetch_analytics(request)

        # GET /v2/video/query/ → stats
        api_request = PlatformAPIRequest(
            platform=Platform.TIKTOK,
            method="POST",
            endpoint="/v2/video/query/",
            body={
                "filters": {"video_ids": [request.post_id]},
                "fields": ["id", "view_count", "like_count", "comment_count", "share_count"],
            },
        )
        api_response = await self._provider.call_platform_api(api_request)
        videos = api_response.data.get("data", {}).get("videos", [{}])
        v = videos[0] if videos else {}
        return AnalyticsData(
            request_id=request.request_id,
            platform=Platform.TIKTOK,
            post_id=request.post_id,
            views=v.get("view_count", 0),
            likes=v.get("like_count", 0),
            comments=v.get("comment_count", 0),
            shares=v.get("share_count", 0),
        )

    async def fetch_trending(self, request: TrendingFetchRequest) -> list[TrendingItem]:
        self._check_kill_switch()

        if isinstance(self._provider, MockProvider):
            return await self._provider.fetch_trending(request)

        # TODO: TikTok Trending API (requires Research API access or web scrape via BrowserUse)
        task = AgentTask(
            description=(
                f"Extract the top {request.limit} trending audio tracks on TikTok"
                + (f" in niches: {', '.join(request.niche_tags)}" if request.niche_tags else "")
                + ". Return as JSON list with fields: audio_title, audio_author, usage_count, growth_rate_pct."
            ),
            url="https://www.tiktok.com/music/trending",
            dry_run=False,
        )
        result = await self._provider.run_agent_task(task)
        raw = result.output.get("trending", [])
        return [
            TrendingItem(platform=Platform.TIKTOK, **item)
            for item in raw[: request.limit]
        ]
