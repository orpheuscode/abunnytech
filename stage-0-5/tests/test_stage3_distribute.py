"""Tests for Stage 3 - Distribution & Engagement."""

from __future__ import annotations

import pytest

from packages.contracts.base import Platform
from packages.contracts.distribution import DistributionStatus
from packages.shared.db import init_db
from stages.stage3_distribute.service import DistributionService


@pytest.mark.asyncio
async def test_post_content_dry_run():
    await init_db()
    svc = DistributionService()
    record = await svc.post_content(
        content_package_id="test-pkg-id",
        platform=Platform.TIKTOK,
        dry_run=True,
    )
    assert record.dry_run is True
    assert record.status == DistributionStatus.DRY_RUN


@pytest.mark.asyncio
async def test_reply_to_comments():
    await init_db()
    svc = DistributionService()
    record = await svc.post_content(
        content_package_id="test-pkg-id",
        platform=Platform.TIKTOK,
        dry_run=True,
    )
    replies = await svc.reply_to_comments(
        distribution_record_id=str(record.id),
        identity_id="test-identity",
    )
    assert len(replies) > 0


@pytest.mark.asyncio
async def test_list_distribution_records():
    await init_db()
    svc = DistributionService()
    await svc.post_content(
        content_package_id="test-pkg-id",
        platform=Platform.INSTAGRAM,
        dry_run=True,
    )
    records = await svc.list_distribution_records()
    assert len(records) >= 1
