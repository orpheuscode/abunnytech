"""LLM, render, and voice adapters for Stage 2 content generation."""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from packages.contracts.base import Platform
from packages.contracts.content import RenderedAsset, SceneBlock, VideoBlueprint
from packages.contracts.identity import IdentityMatrix, VoiceProfile


@runtime_checkable
class ScriptWriterAdapter(Protocol):
    async def generate_script(
        self,
        topic: str,
        identity: IdentityMatrix,
        platform: Platform,
    ) -> list[SceneBlock]:
        """Return ordered scene blocks for a short-form script."""
        ...


@runtime_checkable
class VideoRendererAdapter(Protocol):
    async def render(self, blueprint: VideoBlueprint) -> RenderedAsset:
        ...


@runtime_checkable
class VoiceSynthAdapter(Protocol):
    async def synthesize(self, text: str, voice_profile: VoiceProfile) -> str:
        """Return a local or remote file path to synthesized audio."""
        ...


def _topic_slug(topic: str) -> str:
    return "-".join(topic.lower().split())[:48] or "video"


class MockScriptWriter:
    """Deterministic, realistic short-form scripts (hooks, beats, CTA) for demos."""

    async def generate_script(
        self,
        topic: str,
        identity: IdentityMatrix,
        platform: Platform,
    ) -> list[SceneBlock]:
        name = identity.name or "Creator"
        plat = platform.value
        hook_line = {
            Platform.TIKTOK: f"POV: you finally cracked {topic} and nobody told you this part.",
            Platform.INSTAGRAM: f"Save this — 30 seconds on {topic} that actually lands.",
            Platform.YOUTUBE: f"If you are tired of generic {topic} advice, watch to the end.",
            Platform.TWITTER: f"Hot take on {topic} in under a minute. Thread energy, video form.",
        }.get(platform, f"Stop scrolling — {topic} explained the way {name} wishes they learned it.")

        return [
            SceneBlock(
                order=1,
                duration_seconds=2.5,
                narration_text=hook_line,
                visual_prompt=f"Tight talking-head, neon accent, bold text: {topic.upper()}",
                text_overlay="Wait for it 👀" if platform == Platform.TIKTOK else "Key idea incoming",
                transition="hard_cut",
            ),
            SceneBlock(
                order=2,
                duration_seconds=3.0,
                narration_text=f"Most people bomb {topic} because they skip the setup. Here is the mistake in one line.",
                visual_prompt="Split screen: messy notes vs clean checklist, fast zoom",
                text_overlay="Mistake #1",
                transition="cut",
            ),
            SceneBlock(
                order=3,
                duration_seconds=4.0,
                narration_text=f"As {name}, I keep this dead simple: one idea, one proof, one story. That is the whole format.",
                visual_prompt="B-roll: screen recording + face cam corner",
                text_overlay="The framework",
                transition="swipe",
            ),
            SceneBlock(
                order=4,
                duration_seconds=3.5,
                narration_text=f"Step one: define the outcome for {topic} in plain language. If you cannot, you are not ready to film.",
                visual_prompt="Whiteboard animation style, single keyword per beat",
                text_overlay="Step 1",
                transition="cut",
            ),
            SceneBlock(
                order=5,
                duration_seconds=4.0,
                narration_text="Step two: show the before and after in under five seconds of B-roll. Viewers decide visually first.",
                visual_prompt="Before/after swipe with timer overlay",
                text_overlay="Show, don't tell",
                transition="cut",
            ),
            SceneBlock(
                order=6,
                duration_seconds=3.5,
                narration_text=f"Step three: end with a punchy recap and a {plat}-native CTA. No essays in the outro.",
                visual_prompt="Face cam close-up, confident energy, subtle logo safe zone",
                text_overlay="Recap + CTA",
                transition="fade",
            ),
            SceneBlock(
                order=7,
                duration_seconds=2.5,
                narration_text=f"If this helped with {topic}, follow for the next drop — part two is the advanced version.",
                visual_prompt="End card with handle placeholder and subscribe/follow animation",
                text_overlay="Follow for part 2 🔁" if platform == Platform.TIKTOK else "Subscribe for the deep dive",
                transition="fade",
            ),
        ]


class MockVideoRenderer:
    async def render(self, blueprint: VideoBlueprint) -> RenderedAsset:
        slug = _topic_slug(blueprint.title)
        bid = str(blueprint.id)
        vertical = blueprint.target_platform in (Platform.TIKTOK, Platform.INSTAGRAM)
        return RenderedAsset(
            asset_type="video",
            file_path=f"/mock/renders/{bid}/{slug}.mp4",
            file_url=f"https://cdn.abunnytech.invalid/renders/{bid}/{slug}.mp4",
            format="mp4",
            resolution="1080x1920" if vertical else "1920x1080",
            duration_seconds=float(blueprint.target_duration_seconds),
            file_size_bytes=3_200_000,
        )


class MockVoiceSynth:
    async def synthesize(self, text: str, voice_profile: VoiceProfile) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        vid = voice_profile.voice_id or "mock-voice"
        return f"/mock/audio/{vid}_{digest}.wav"


class OpenAIScriptWriter:
    """TODO: Integrate OpenAI (chat/completions or responses API) for scene generation."""

    async def generate_script(
        self,
        topic: str,
        identity: IdentityMatrix,
        platform: Platform,
    ) -> list[SceneBlock]:
        raise NotImplementedError("OpenAIScriptWriter: wire API key and prompt templates.")


class ElevenLabsVoiceSynth:
    """TODO: Integrate ElevenLabs text-to-speech; write bytes to object storage and return path/URL."""

    async def synthesize(self, text: str, voice_profile: VoiceProfile) -> str:
        raise NotImplementedError("ElevenLabsVoiceSynth: wire API key and voice_id.")
