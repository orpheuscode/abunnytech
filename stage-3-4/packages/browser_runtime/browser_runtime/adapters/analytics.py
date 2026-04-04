"""
Analytics dashboard adapter (Stage 4 — Analyze & Adapt).

Aggregates performance metrics from multiple platforms into a single
AnalyticsData record.  Also provides a cross-platform summary helper
for the Streamlit dashboard.

This adapter does not post content or send messages — it is read-only.
"""
from __future__ import annotations

from datetime import datetime

from ..audit import AuditLogger
from ..providers.base import BrowserProvider
from ..providers.mock import MockProvider
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
from .base import PlatformAdapter
from .instagram import InstagramAdapter
from .tiktok import TikTokAdapter


class AnalyticsAdapter(PlatformAdapter):
    """
    Aggregates analytics from TikTok and Instagram into a combined record.

    Also exposes cross-platform summary for the dashboard.
    """

    def __init__(self, provider: BrowserProvider, audit: AuditLogger | None = None) -> None:
        super().__init__(provider, audit)
        self._tiktok = TikTokAdapter(provider, audit)
        self._instagram = InstagramAdapter(provider, audit)

    @property
    def platform(self) -> Platform:
        return Platform.ANALYTICS

    async def post_content(self, request: PostContentRequest) -> PostContentResult:
        raise NotImplementedError("AnalyticsAdapter is read-only.")

    async def reply_to_comment(self, request: CommentReplyRequest) -> CommentReplyResult:
        raise NotImplementedError("AnalyticsAdapter is read-only.")

    async def send_dm(self, request: DMRequest) -> DMResult:
        raise NotImplementedError("AnalyticsAdapter is read-only.")

    async def fetch_analytics(self, request: AnalyticsFetchRequest) -> AnalyticsData:
        """
        Fetch analytics from the platform specified in request.platform.
        If platform is ANALYTICS, aggregates TikTok + Instagram.
        """
        self._check_kill_switch()

        if request.platform == Platform.ANALYTICS:
            return await self._aggregate(request)

        if request.platform == Platform.TIKTOK:
            return await self._tiktok.fetch_analytics(request)

        if request.platform == Platform.INSTAGRAM:
            return await self._instagram.fetch_analytics(request)

        if isinstance(self._provider, MockProvider):
            return await self._provider.fetch_analytics(request)

        raise ValueError(f"AnalyticsAdapter: unsupported platform {request.platform}")

    async def _aggregate(self, request: AnalyticsFetchRequest) -> AnalyticsData:
        """Sum metrics across TikTok and Instagram for the same post/period."""
        tt_req = AnalyticsFetchRequest(
            request_id=request.request_id + "_tt",
            platform=Platform.TIKTOK,
            post_id=request.post_id,
            account_id=request.account_id,
            since=request.since,
            until=request.until,
        )
        ig_req = AnalyticsFetchRequest(
            request_id=request.request_id + "_ig",
            platform=Platform.INSTAGRAM,
            post_id=request.post_id,
            account_id=request.account_id,
            since=request.since,
            until=request.until,
        )
        tt = await self._tiktok.fetch_analytics(tt_req)
        ig = await self._instagram.fetch_analytics(ig_req)

        return AnalyticsData(
            request_id=request.request_id,
            platform=Platform.ANALYTICS,
            post_id=request.post_id,
            views=tt.views + ig.views,
            likes=tt.likes + ig.likes,
            comments=tt.comments + ig.comments,
            shares=tt.shares + ig.shares,
            saves=tt.saves + ig.saves,
            follows_gained=tt.follows_gained + ig.follows_gained,
            watch_time_avg_seconds=(tt.watch_time_avg_seconds + ig.watch_time_avg_seconds) / 2,
            completion_rate_pct=(tt.completion_rate_pct + ig.completion_rate_pct) / 2,
        )

    async def fetch_trending(self, request: TrendingFetchRequest) -> list[TrendingItem]:
        """Fetch trending items from TikTok and Instagram combined."""
        self._check_kill_switch()
        tt_req = TrendingFetchRequest(
            platform=Platform.TIKTOK,
            niche_tags=request.niche_tags,
            limit=request.limit,
        )
        ig_req = TrendingFetchRequest(
            platform=Platform.INSTAGRAM,
            niche_tags=request.niche_tags,
            limit=request.limit,
        )
        tt_items = await self._tiktok.fetch_trending(tt_req)
        ig_items = await self._instagram.fetch_trending(ig_req)
        combined = tt_items + ig_items
        combined.sort(key=lambda x: x.usage_count, reverse=True)
        return combined[: request.limit]

    async def cross_platform_summary(
        self,
        post_ids: dict[Platform, str],
        since: datetime | None = None,
    ) -> dict[str, AnalyticsData]:
        """
        Convenience method for the Streamlit dashboard.

        Args:
            post_ids: {Platform.TIKTOK: "tt_post_id", Platform.INSTAGRAM: "ig_post_id"}
            since: optional start of window

        Returns:
            dict keyed by platform value string → AnalyticsData
        """
        results = {}
        for platform, post_id in post_ids.items():
            req = AnalyticsFetchRequest(
                platform=platform,
                post_id=post_id,
                since=since,
            )
            results[platform.value] = await self.fetch_analytics(req)
        return results
