from __future__ import annotations

from abc import ABC, abstractmethod

import packages.shared.config as config
from packages.contracts.identity import AvatarProfile, IdentityMatrix, VoiceProfile


class VoiceProviderAdapter(ABC):
    @abstractmethod
    async def generate_voice_pack(self, identity: IdentityMatrix) -> VoiceProfile:
        raise NotImplementedError


class AvatarProviderAdapter(ABC):
    @abstractmethod
    async def generate_avatar(self, identity: IdentityMatrix) -> AvatarProfile:
        raise NotImplementedError


class MockVoiceProvider(VoiceProviderAdapter):
    async def generate_voice_pack(self, identity: IdentityMatrix) -> VoiceProfile:
        slug = identity.name.lower().replace(" ", "_")[:32]
        return VoiceProfile(
            voice_id=f"mock_voice_{slug}",
            provider="mock",
            pitch=1.0,
            speed=1.05,
            style="warm-conversational",
            sample_url=f"https://example.com/audio/{slug}_demo.mp3",
        )


class MockAvatarProvider(AvatarProviderAdapter):
    async def generate_avatar(self, identity: IdentityMatrix) -> AvatarProfile:
        slug = identity.name.lower().replace(" ", "_")[:32]
        return AvatarProfile(
            avatar_url=f"https://example.com/avatars/{slug}.png",
            style="stylized-3d",
            background_color="#1a1a2e",
            overlay_template="corner-badge",
        )


class ElevenLabsVoiceProvider(VoiceProviderAdapter):
    def __init__(self) -> None:
        self._settings = config.get_settings()

    async def generate_voice_pack(self, identity: IdentityMatrix) -> VoiceProfile:
        # TODO: Instantiate ElevenLabs client with self._settings.elevenlabs_api_key
        # TODO: Map identity (archetype, name) to voice selection or clone workflow
        # TODO: Call voices API / text-to-speech preview to produce sample_url
        _ = identity
        _ = self._settings.elevenlabs_api_key
        return VoiceProfile(
            voice_id="",
            provider="elevenlabs",
            pitch=1.0,
            speed=1.0,
            style="neutral",
            sample_url="",
        )
