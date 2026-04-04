"""Tests for platform adapters using MockProvider."""
from __future__ import annotations

import pytest

from browser_runtime.adapters import get_adapter
from browser_runtime.adapters.analytics import AnalyticsAdapter
from browser_runtime.adapters.instagram import InstagramAdapter
from browser_runtime.adapters.shopify import ShopifyAdapter
from browser_runtime.adapters.tiktok import TikTokAdapter
from browser_runtime.providers.mock import MockProvider
from browser_runtime.types import (
    AnalyticsFetchRequest,
    CommentReplyRequest,
    DMRequest,
    Platform,
    PostContentRequest,
    TrendingFetchRequest,
)


@pytest.fixture
def provider():
    return MockProvider(dry_run=True)


@pytest.fixture
def tiktok(provider):
    return TikTokAdapter(provider)


@pytest.fixture
def instagram(provider):
    return InstagramAdapter(provider)


@pytest.fixture
def analytics(provider):
    return AnalyticsAdapter(provider)


class TestGetAdapterFactory:
    def test_returns_tiktok_adapter(self, provider):
        a = get_adapter("tiktok", provider)
        assert isinstance(a, TikTokAdapter)

    def test_returns_instagram_adapter(self, provider):
        a = get_adapter("instagram", provider)
        assert isinstance(a, InstagramAdapter)

    def test_returns_shopify_adapter(self, provider):
        a = get_adapter("shopify", provider)
        assert isinstance(a, ShopifyAdapter)

    def test_returns_analytics_adapter(self, provider):
        a = get_adapter("analytics", provider)
        assert isinstance(a, AnalyticsAdapter)

    def test_unknown_platform_raises(self, provider):
        with pytest.raises(ValueError):
            get_adapter("myspace", provider)


class TestTikTokAdapter:
    async def test_post_content_dry_run(self, tiktok):
        req = PostContentRequest(
            platform=Platform.TIKTOK,
            caption="Test video #AI #tech",
            dry_run=True,
        )
        result = await tiktok.post_content(req)
        assert result.success
        assert result.dry_run
        assert result.post_id.startswith("DRY-RUN-")

    async def test_post_content_records_in_provider(self, provider, tiktok):
        req = PostContentRequest(platform=Platform.TIKTOK, caption="hi", dry_run=True)
        await tiktok.post_content(req)
        assert len(provider.calls["post_content"]) == 1

    async def test_ai_disclosure_enforced(self, tiktok):
        req = PostContentRequest(
            platform=Platform.TIKTOK,
            caption="sneaky post",
            ai_disclosure=False,
            dry_run=True,
        )
        with pytest.raises(ValueError, match="ai_disclosure must be True"):
            await tiktok.post_content(req)

    async def test_reply_to_comment(self, tiktok):
        req = CommentReplyRequest(
            platform=Platform.TIKTOK,
            post_id="p1",
            comment_id="c1",
            reply_text="Great point! (AI-assisted reply)",
            dry_run=True,
        )
        result = await tiktok.reply_to_comment(req)
        assert result.success

    async def test_fetch_analytics(self, tiktok):
        req = AnalyticsFetchRequest(platform=Platform.TIKTOK, post_id="p1")
        data = await tiktok.fetch_analytics(req)
        assert data.views >= 0

    async def test_fetch_trending(self, tiktok):
        req = TrendingFetchRequest(platform=Platform.TIKTOK, limit=2)
        items = await tiktok.fetch_trending(req)
        assert len(items) <= 2

    async def test_send_dm_raises_not_implemented_without_mock(self):
        """TikTok DM via non-mock provider requires partner access."""
        from browser_runtime.providers.platform_api import PlatformAPIProvider
        real_provider = PlatformAPIProvider(dry_run=True)
        adapter = TikTokAdapter(real_provider)
        req = DMRequest(
            platform=Platform.TIKTOK,
            recipient_id="user1",
            message="hi",
            dry_run=True,
        )
        with pytest.raises(NotImplementedError, match="partner"):
            await adapter.send_dm(req)


class TestInstagramAdapter:
    async def test_post_content_dry_run(self, instagram):
        req = PostContentRequest(
            platform=Platform.INSTAGRAM,
            caption="Reel content #AI",
            dry_run=True,
        )
        result = await instagram.post_content(req)
        assert result.success

    async def test_ai_disclosure_enforced(self, instagram):
        req = PostContentRequest(
            platform=Platform.INSTAGRAM,
            caption="test",
            ai_disclosure=False,
            dry_run=True,
        )
        with pytest.raises(ValueError):
            await instagram.post_content(req)

    async def test_reply_to_comment(self, instagram):
        req = CommentReplyRequest(
            platform=Platform.INSTAGRAM,
            post_id="post_ig_1",
            comment_id="comment_ig_1",
            reply_text="Thanks! 🤖",
            dry_run=True,
        )
        result = await instagram.reply_to_comment(req)
        assert result.success

    async def test_fetch_analytics(self, instagram):
        req = AnalyticsFetchRequest(platform=Platform.INSTAGRAM, post_id="ig_post_1")
        data = await instagram.fetch_analytics(req)
        assert data.platform == Platform.INSTAGRAM


class TestShopifyAdapter:
    async def test_post_content_raises(self, provider):
        adapter = ShopifyAdapter(provider)
        with pytest.raises(NotImplementedError):
            await adapter.post_content(PostContentRequest(platform=Platform.SHOPIFY, caption="x"))

    async def test_fetch_analytics_mock(self, provider):
        adapter = ShopifyAdapter(provider)
        req = AnalyticsFetchRequest(platform=Platform.SHOPIFY)
        data = await adapter.fetch_analytics(req)
        assert data.platform == Platform.SHOPIFY


class TestAnalyticsAdapter:
    async def test_aggregates_both_platforms(self, analytics):
        req = AnalyticsFetchRequest(platform=Platform.ANALYTICS, post_id="p1")
        data = await analytics.fetch_analytics(req)
        # Aggregated = TikTok + Instagram mock values
        assert data.views > 0
        assert data.platform == Platform.ANALYTICS

    async def test_cross_platform_summary(self, analytics):
        summary = await analytics.cross_platform_summary({
            Platform.TIKTOK: "tt_post_1",
            Platform.INSTAGRAM: "ig_post_1",
        })
        assert Platform.TIKTOK.value in summary
        assert Platform.INSTAGRAM.value in summary
        for data in summary.values():
            assert data.views >= 0

    async def test_fetch_trending_combined(self, analytics):
        req = TrendingFetchRequest(platform=Platform.ANALYTICS, limit=5)
        items = await analytics.fetch_trending(req)
        # Should have items from both TikTok and Instagram fixtures
        platforms = {item.platform for item in items}
        assert Platform.TIKTOK in platforms
