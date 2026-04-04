"""Tests for Stage 0 - Identity Matrix."""

from __future__ import annotations

import pytest

from packages.contracts.base import Platform
from packages.contracts.identity import PersonaArchetype
from packages.shared.db import init_db
from stages.stage0_identity.adapters import MockAvatarProvider, MockVoiceProvider
from stages.stage0_identity.service import create_default_identity, create_identity, list_identities


@pytest.mark.asyncio
async def test_create_default_identity():
    await init_db()
    identity = await create_default_identity()
    assert identity.name == "Avery Bytes"
    assert identity.archetype == PersonaArchetype.EDUCATOR
    assert identity.voice.provider == "mock"
    assert identity.avatar.style == "stylized-3d"
    assert len(identity.platforms) == 2


@pytest.mark.asyncio
async def test_create_custom_identity():
    await init_db()
    identity = await create_identity(
        name="TestBot",
        archetype=PersonaArchetype.ENTERTAINER,
        topics=["comedy", "memes"],
        platforms=[Platform.TIKTOK],
    )
    assert identity.name == "TestBot"
    assert identity.archetype == PersonaArchetype.ENTERTAINER
    assert len(identity.guidelines.topics) == 2


@pytest.mark.asyncio
async def test_list_identities():
    await init_db()
    await create_default_identity()
    identities = await list_identities()
    assert len(identities) >= 1


@pytest.mark.asyncio
async def test_mock_voice_provider():
    from packages.contracts.identity import IdentityMatrix
    provider = MockVoiceProvider()
    identity = IdentityMatrix(name="Test", archetype=PersonaArchetype.EDUCATOR)
    voice = await provider.generate_voice_pack(identity)
    assert voice.provider == "mock"
    assert "test" in voice.voice_id


@pytest.mark.asyncio
async def test_mock_avatar_provider():
    from packages.contracts.identity import IdentityMatrix
    provider = MockAvatarProvider()
    identity = IdentityMatrix(name="Test", archetype=PersonaArchetype.EDUCATOR)
    avatar = await provider.generate_avatar(identity)
    assert "test" in avatar.avatar_url
