"""Tests for Stage 1 - Discovery & Analysis."""

from __future__ import annotations

import pytest

from packages.contracts.base import Platform
from packages.shared.db import init_db
from stages.stage1_discover.service import DiscoveryService


@pytest.mark.asyncio
async def test_discover_trending():
    await init_db()
    svc = DiscoveryService()
    trends = await svc.discover_trending(Platform.TIKTOK, "test-identity")
    assert len(trends) > 0
    assert all(t.platform == Platform.TIKTOK for t in trends)


@pytest.mark.asyncio
async def test_analyze_competitors():
    await init_db()
    svc = DiscoveryService()
    results = await svc.analyze_competitors(Platform.TIKTOK, ["@rival1", "@rival2"], "test-identity")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_build_training_manifest():
    await init_db()
    from packages.contracts.discovery import TrainingMaterial
    svc = DiscoveryService()
    materials = [
        TrainingMaterial(
            source_url="https://example.com/v1",
            platform=Platform.TIKTOK,
            tags=["AI", "productivity"],
        ),
    ]
    manifest = await svc.build_training_manifest("test-identity", materials)
    assert manifest.identity_id == "test-identity"
    assert len(manifest.materials) == 1
