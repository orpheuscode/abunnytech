"""Tests for PostingExecutor and MockPlatformAdapter."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from browser_runtime.audit import AuditLogger, override_audit
from browser_runtime.types import ProviderType

from ..adapters.mock import MockPlatformAdapter
from ..contracts import DistributionStatus, Platform
from ..executor import PostingExecutor
from ..scheduler import PlatformTarget, PostingScheduler, PostingWindow
from .fixtures import make_identity, make_package


@pytest.fixture(autouse=True)
def silence_audit(tmp_path):
    """Route audit logs to a temp file so tests don't litter the working dir."""
    override_audit(AuditLogger(str(tmp_path / "audit.jsonl")))


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.provider_type = ProviderType.MOCK
    return provider


@pytest.fixture
def adapter(mock_provider):
    return MockPlatformAdapter(provider=mock_provider, dry_run=True)


@pytest.fixture
def executor(adapter):
    return PostingExecutor(adapter=adapter, dry_run=True)


@pytest.fixture
def scheduled_post():
    targets = [
        PlatformTarget(
            platform=Platform.TIKTOK,
            window=PostingWindow(start_hour=0, end_hour=23),
        )
    ]
    scheduler = PostingScheduler(targets=targets, dry_run=True)
    package = make_package(target_platforms=[Platform.TIKTOK])
    posts = scheduler.enqueue(package, now=datetime(2026, 4, 4, 12, 0, 0))
    return posts[0]


@pytest.mark.asyncio
async def test_execute_post_dry_run_returns_dry_run_status(executor, scheduled_post):
    identity = make_identity()
    record = await executor.execute_post(scheduled_post, identity)

    assert record.status == DistributionStatus.DRY_RUN
    assert record.dry_run is True
    assert record.package_id == scheduled_post.package.package_id
    assert record.platform == Platform.TIKTOK


@pytest.mark.asyncio
async def test_execute_post_appends_ai_disclosure_to_caption(executor, scheduled_post):
    identity = make_identity()
    record = await executor.execute_post(scheduled_post, identity)

    assert "✨ AI-assisted" in record.caption_used
    assert identity.persona_name in record.caption_used


@pytest.mark.asyncio
async def test_execute_post_includes_hashtags(executor, scheduled_post):
    identity = make_identity()
    record = await executor.execute_post(scheduled_post, identity)

    assert record.hashtags_used == scheduled_post.package.hashtags


@pytest.mark.asyncio
async def test_execute_comment_reply_dry_run(executor):
    result = await executor.execute_comment_reply(
        platform=Platform.TIKTOK,
        post_id="post-001",
        comment_id="comment-001",
        reply_text="Thank you! 🥰",
    )
    assert result.success is True
    assert result.dry_run is True


@pytest.mark.asyncio
async def test_execute_dm_always_sets_ai_disclosure(adapter, mock_provider):
    """Verify ai_disclosure=True is set on every DM regardless of other params."""
    received_requests = []

    original_do_send_dm = adapter._do_send_dm

    async def capture_and_call(request):
        received_requests.append(request)
        return await original_do_send_dm(request)

    adapter._do_send_dm = capture_and_call
    # Switch to non-dry-run mode so the real method is called
    adapter._dry_run = False

    executor_live = PostingExecutor(adapter=adapter, dry_run=False)
    await executor_live.execute_dm(
        platform=Platform.INSTAGRAM,
        recipient_id="user-123",
        message="Hey! Check this out",
    )

    assert len(received_requests) == 1
    assert received_requests[0].ai_disclosure is True


@pytest.mark.asyncio
async def test_mock_adapter_post_content_returns_fake_post_id(adapter):
    from browser_runtime.types import Platform as BP
    from browser_runtime.types import PostContentRequest
    request = PostContentRequest(
        platform=BP.TIKTOK,
        caption="Test caption",
        dry_run=False,
        ai_disclosure=True,
    )
    # Force non-dry-run path on the adapter
    adapter._dry_run = False
    result = await adapter.post_content(request)

    assert result.success is True
    assert result.post_id is not None
    assert result.post_url is not None
