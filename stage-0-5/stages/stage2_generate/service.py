"""Stage 2: blueprint creation, scene generation, and mock render pipeline."""

from __future__ import annotations

from uuid import UUID

import structlog

from packages.contracts.base import Platform, new_id
from packages.contracts.content import (
    ContentPackage,
    ContentStatus,
    RenderedAsset,
    SceneBlock,
    VideoBlueprint,
)
from packages.contracts.identity import (
    IdentityMatrix,
    PersonaArchetype,
    PlatformPresence,
    VoiceProfile,
)
from packages.shared.db import (
    get_record,
    list_pipeline_records,
    log_audit,
    store_record,
)
from stages.stage2_generate.adapters import (
    MockScriptWriter,
    MockVideoRenderer,
    MockVoiceSynth,
    ScriptWriterAdapter,
    VideoRendererAdapter,
    VoiceSynthAdapter,
)

log = structlog.get_logger(__name__)

STAGE = "stage2"
CONTRACT_BLUEPRINT = "VideoBlueprint"
CONTRACT_PACKAGE = "ContentPackage"


def _placeholder_identity(identity_id: str, platform: Platform) -> IdentityMatrix:
    try:
        uid = UUID(identity_id)
    except ValueError:
        uid = new_id()
    return IdentityMatrix(
        id=uid,
        name="Creator",
        archetype=PersonaArchetype.EDUCATOR,
        tagline="Short-form that actually teaches something",
        platforms=[PlatformPresence(platform=platform, handle="@creator")],
    )


def _platform_for_script(identity: IdentityMatrix, fallback: Platform) -> Platform:
    if identity.platforms:
        return identity.platforms[0].platform
    return fallback


def _hashtags_for(topic: str, platform: Platform) -> list[str]:
    words = [w.strip("#") for w in topic.split() if len(w.strip("#")) > 2][:4]
    tags = [w if w.startswith("#") else f"#{w}" for w in words]
    extras = {
        Platform.TIKTOK: ["#fyp", "#LearnOnTikTok"],
        Platform.INSTAGRAM: ["#reels", "#explorepage"],
        Platform.YOUTUBE: ["#Shorts", "#YouTubeShorts"],
        Platform.TWITTER: ["#Video", "#Growth"],
    }
    return list(dict.fromkeys(tags + extras.get(platform, [])))


def _normalize_scenes(scenes: list[SceneBlock], count: int) -> list[SceneBlock]:
    if count <= 0:
        return []
    picked = scenes[:count]
    if len(picked) < count:
        for i in range(len(picked), count):
            picked.append(
                SceneBlock(
                    order=i + 1,
                    duration_seconds=2.5,
                    narration_text=f"Bonus beat {i + 1}: keep watching — payoff still loading.",
                    visual_prompt="Fast montage, kinetic text, high energy",
                    text_overlay="Stay tuned",
                    transition="cut",
                )
            )
    return [
        SceneBlock(
            order=i + 1,
            duration_seconds=s.duration_seconds,
            narration_text=s.narration_text,
            visual_prompt=s.visual_prompt,
            text_overlay=s.text_overlay,
            transition=s.transition,
        )
        for i, s in enumerate(picked)
    ]


class ContentGenerationService:
    def __init__(
        self,
        script_writer: ScriptWriterAdapter | None = None,
        video_renderer: VideoRendererAdapter | None = None,
        voice_synth: VoiceSynthAdapter | None = None,
    ) -> None:
        self._script = script_writer or MockScriptWriter()
        self._renderer = video_renderer or MockVideoRenderer()
        self._voice = voice_synth or MockVoiceSynth()

    async def generate_scenes(
        self,
        topic: str,
        identity: IdentityMatrix,
        count: int,
    ) -> list[SceneBlock]:
        platform = _platform_for_script(identity, Platform.TIKTOK)
        await log_audit(
            STAGE,
            "generate_scenes",
            topic=topic,
            identity_id=str(identity.id),
            count=count,
            platform=platform.value,
        )
        log.info(
            "generate_scenes",
            topic=topic,
            identity_id=str(identity.id),
            count=count,
            platform=platform.value,
        )
        raw = await self._script.generate_script(topic, identity, platform)
        scenes = _normalize_scenes(raw, count)
        await log_audit(
            STAGE,
            "generate_scenes_done",
            topic=topic,
            scene_count=len(scenes),
        )
        return scenes

    async def create_blueprint(
        self,
        identity_id: str,
        title: str,
        topic: str,
        platform: Platform,
        *,
        scene_count: int = 7,
    ) -> VideoBlueprint:
        await log_audit(
            STAGE,
            "blueprint_create_start",
            identity_id=identity_id,
            title=title,
            topic=topic,
            platform=platform.value,
        )
        log.info(
            "blueprint_create_start",
            identity_id=identity_id,
            title=title,
            topic=topic,
        )
        identity = _placeholder_identity(identity_id, platform)
        scenes = await self.generate_scenes(topic, identity, scene_count)
        hook = scenes[0].narration_text[:280] if scenes else f"Why {topic} matters now"
        cta = scenes[-1].narration_text[:200] if scenes else "Follow for more."
        total_duration = int(sum(s.duration_seconds for s in scenes)) or 30

        blueprint = VideoBlueprint(
            identity_id=identity_id,
            title=title,
            hook=hook,
            scenes=scenes,
            target_platform=platform,
            target_duration_seconds=min(max(total_duration, 15), 90),
            hashtags=_hashtags_for(topic, platform),
            cta=cta,
            status=ContentStatus.DRAFT,
        )
        blueprint.add_audit("blueprint_created", actor="stage2", topic=topic)

        payload = blueprint.model_dump(mode="json")
        await store_record(CONTRACT_BLUEPRINT, STAGE, payload, identity_id=identity_id)
        await log_audit(
            STAGE,
            "blueprint_created",
            identity_id=identity_id,
            blueprint_id=str(blueprint.id),
            title=title,
        )
        log.info("blueprint_created", blueprint_id=str(blueprint.id))
        return blueprint

    async def render_content(self, blueprint_id: str) -> ContentPackage:
        await log_audit(STAGE, "render_start", blueprint_id=blueprint_id)
        log.info("render_start", blueprint_id=blueprint_id)

        raw = await get_record(blueprint_id)
        if raw is None:
            await log_audit(STAGE, "render_failed", blueprint_id=blueprint_id, reason="not_found")
            msg = f"Blueprint not found: {blueprint_id}"
            raise ValueError(msg)

        blueprint = VideoBlueprint.model_validate(raw)
        blueprint.status = ContentStatus.RENDERING
        blueprint.add_audit("render_started", actor="stage2")

        narration = " ".join(s.narration_text for s in blueprint.scenes)
        voice_profile = VoiceProfile(voice_id=blueprint.audio_id or "mock-default")
        audio_path = await self._voice.synthesize(narration, voice_profile)
        video_asset = await self._renderer.render(blueprint)

        audio_asset = RenderedAsset(
            asset_type="narration_audio",
            file_path=audio_path,
            file_url=f"https://cdn.abunnytech.invalid/audio/{blueprint.id}.wav",
            format="wav",
            resolution="n/a",
            duration_seconds=float(blueprint.target_duration_seconds),
            file_size_bytes=480_000,
        )

        caption = f"{blueprint.hook}\n\n{blueprint.cta}".strip()
        package = ContentPackage(
            identity_id=blueprint.identity_id,
            blueprint_id=str(blueprint.id),
            title=blueprint.title,
            caption=caption,
            hashtags=blueprint.hashtags,
            target_platform=blueprint.target_platform,
            assets=[video_asset, audio_asset],
            status=ContentStatus.RENDERED,
        )
        package.add_audit("package_rendered", actor="stage2", blueprint_id=blueprint_id)

        await store_record(
            CONTRACT_PACKAGE,
            STAGE,
            package.model_dump(mode="json"),
            identity_id=blueprint.identity_id,
        )
        await log_audit(
            STAGE,
            "render_complete",
            blueprint_id=blueprint_id,
            package_id=str(package.id),
        )
        log.info("render_complete", package_id=str(package.id), blueprint_id=blueprint_id)
        return package

    async def list_blueprints(self) -> list[VideoBlueprint]:
        rows = await list_pipeline_records(CONTRACT_BLUEPRINT, STAGE)
        return [VideoBlueprint.model_validate(r) for r in rows]

    async def list_packages(self) -> list[ContentPackage]:
        rows = await list_pipeline_records(CONTRACT_PACKAGE, STAGE)
        return [ContentPackage.model_validate(r) for r in rows]
