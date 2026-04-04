"""Tests for Stage 2 - Content Generation."""

from __future__ import annotations

import pytest

from packages.contracts.base import Platform
from packages.shared.db import init_db
from stages.stage2_generate.service import ContentGenerationService


@pytest.mark.asyncio
async def test_create_blueprint():
    await init_db()
    svc = ContentGenerationService()
    bp = await svc.create_blueprint(
        identity_id="test-identity",
        title="Test Video",
        topic="AI tools",
        platform=Platform.TIKTOK,
    )
    assert bp.title == "Test Video"
    assert len(bp.scenes) > 0
    assert bp.target_platform == Platform.TIKTOK


@pytest.mark.asyncio
async def test_render_content():
    await init_db()
    svc = ContentGenerationService()
    bp = await svc.create_blueprint(
        identity_id="test-identity",
        title="Render Test",
        topic="productivity",
        platform=Platform.TIKTOK,
    )
    package = await svc.render_content(str(bp.id))
    assert package.blueprint_id == str(bp.id)
    assert len(package.assets) >= 1
    assert package.title == "Render Test"


@pytest.mark.asyncio
async def test_list_blueprints():
    await init_db()
    svc = ContentGenerationService()
    await svc.create_blueprint(
        identity_id="test-identity",
        title="List Test",
        topic="tech",
        platform=Platform.YOUTUBE,
    )
    bps = await svc.list_blueprints()
    assert len(bps) >= 1
