"""Tests for MockProvider — the primary offline/CI provider."""
from __future__ import annotations

import pytest

from browser_runtime.config import BrowserRuntimeSettings, KillSwitchConfig, override_settings
from browser_runtime.providers.mock import MockProvider
from browser_runtime.session import KillSwitchTriggered
from browser_runtime.types import (
    AgentTask,
    AnalyticsFetchRequest,
    CommentReplyRequest,
    DMRequest,
    ExtractionSchema,
    Platform,
    PlatformAPIRequest,
    PostContentRequest,
    SkillRequest,
    TrendingFetchRequest,
)


class TestMockProviderAgentTask:
    async def test_run_agent_task_success(self, mock_provider):
        task = AgentTask(description="Click the like button", dry_run=True)
        result = await mock_provider.run_agent_task(task)
        assert result.success
        assert result.task_id == task.task_id
        assert result.dry_run is True

    async def test_run_agent_task_records_call(self, mock_provider):
        task = AgentTask(description="test task")
        await mock_provider.run_agent_task(task)
        assert len(mock_provider.calls["run_agent_task"]) == 1
        assert mock_provider.calls["run_agent_task"][0]["task_id"] == task.task_id

    async def test_inject_failure(self, mock_provider):
        mock_provider.inject_failure("run_agent_task", RuntimeError("simulated failure"))
        task = AgentTask(description="will fail")
        with pytest.raises(RuntimeError, match="simulated failure"):
            await mock_provider.run_agent_task(task)

    async def test_failure_consumed_after_one_use(self, mock_provider):
        mock_provider.inject_failure("run_agent_task", RuntimeError("once"))
        with pytest.raises(RuntimeError):
            await mock_provider.run_agent_task(AgentTask(description="first"))
        # Second call should succeed
        result = await mock_provider.run_agent_task(AgentTask(description="second"))
        assert result.success


class TestMockProviderBulkExtract:
    async def test_bulk_extract_all_succeed(self, mock_provider):
        schema = ExtractionSchema(fields={"title": "page title", "views": "view count"})
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        results = await mock_provider.bulk_extract(urls, schema)
        assert len(results) == 3
        assert all(r.success for r in results)
        assert all("title" in r.data and "views" in r.data for r in results)

    async def test_bulk_extract_empty_urls(self, mock_provider):
        schema = ExtractionSchema(fields={"x": "y"})
        results = await mock_provider.bulk_extract([], schema)
        assert results == []


class TestMockProviderSkill:
    async def test_invoke_skill(self, mock_provider):
        req = SkillRequest(skill_name="like_post", params={"post_id": "123"})
        result = await mock_provider.invoke_skill(req)
        assert result.success
        assert result.skill_name == "like_post"


class TestMockProviderPlatformAPI:
    async def test_call_platform_api(self, mock_provider):
        req = PlatformAPIRequest(
            platform=Platform.TIKTOK,
            endpoint="/v2/video/query/",
            dry_run=True,
        )
        resp = await mock_provider.call_platform_api(req)
        assert resp.status_code == 200
        assert resp.dry_run is True


class TestMockProviderAdapterHelpers:
    async def test_post_content_dry_run(self, mock_provider):
        req = PostContentRequest(
            platform=Platform.TIKTOK,
            caption="Hello world #AI",
            dry_run=True,
        )
        result = await mock_provider.post_content(req)
        assert result.success
        assert result.post_id.startswith("DRY-RUN-")
        assert result.dry_run is True

    async def test_post_content_live_mock(self, live_mock_provider):
        req = PostContentRequest(
            platform=Platform.INSTAGRAM,
            caption="Live mock post",
            dry_run=False,
        )
        result = await live_mock_provider.post_content(req)
        assert result.success
        assert not result.post_id.startswith("DRY-RUN-")

    async def test_reply_comment(self, mock_provider):
        req = CommentReplyRequest(
            platform=Platform.TIKTOK,
            post_id="post_abc",
            comment_id="comment_xyz",
            reply_text="Thanks! 🤖 (AI-generated)",
            dry_run=True,
        )
        result = await mock_provider.reply_comment(req)
        assert result.success
        assert result.reply_id.startswith("DRY-RUN-")

    async def test_send_dm(self, mock_provider):
        req = DMRequest(
            platform=Platform.INSTAGRAM,
            recipient_id="user_123",
            message="Hey! This is an AI-assisted reply.",
            ai_disclosure=True,
            dry_run=True,
        )
        result = await mock_provider.send_dm(req)
        assert result.success

    async def test_fetch_analytics(self, mock_provider):
        req = AnalyticsFetchRequest(platform=Platform.TIKTOK, post_id="post_123")
        data = await mock_provider.fetch_analytics(req)
        assert data.views > 0
        assert data.likes > 0
        assert 0 <= data.completion_rate_pct <= 100

    async def test_fetch_trending_tiktok(self, mock_provider):
        req = TrendingFetchRequest(platform=Platform.TIKTOK, limit=3)
        items = await mock_provider.fetch_trending(req)
        assert len(items) <= 3
        assert all(item.platform == Platform.TIKTOK for item in items)
        assert all(item.audio_title for item in items)

    async def test_fetch_trending_instagram(self, mock_provider):
        req = TrendingFetchRequest(platform=Platform.INSTAGRAM, limit=2)
        items = await mock_provider.fetch_trending(req)
        assert len(items) <= 2

    async def test_fetch_trending_unknown_platform_returns_empty(self, mock_provider):
        req = TrendingFetchRequest(platform=Platform.SHOPIFY, limit=5)
        items = await mock_provider.fetch_trending(req)
        assert items == []


class TestMockProviderKillSwitch:
    async def test_global_kill_switch_blocks_all(self):
        settings = BrowserRuntimeSettings(
            dry_run=True,
            global_kill_switch=KillSwitchConfig(enabled=True, reason="emergency stop"),
        )
        override_settings(settings)
        provider = MockProvider(dry_run=True)

        with pytest.raises(KillSwitchTriggered, match="emergency stop"):
            await provider.run_agent_task(AgentTask(description="blocked"))

    async def test_platform_kill_switch_blocks_platform_calls(self):
        from browser_runtime.config import PlatformConfig
        settings = BrowserRuntimeSettings(
            dry_run=True,
            tiktok=PlatformConfig(kill_switch=KillSwitchConfig(enabled=True, reason="tiktok down")),
        )
        override_settings(settings)
        provider = MockProvider(dry_run=True)

        req = PostContentRequest(platform=Platform.TIKTOK, caption="test", dry_run=True)
        with pytest.raises(KillSwitchTriggered, match="tiktok down"):
            await provider.post_content(req)
