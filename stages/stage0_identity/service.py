from __future__ import annotations

import json
from uuid import UUID

import structlog
from sqlalchemy import select

import packages.shared.config as config
from packages.contracts.base import Platform
from packages.contracts.identity import (
    ContentGuidelines,
    IdentityMatrix,
    PersonaArchetype,
    PlatformPresence,
)
from packages.shared.db import (
    PipelineRecord,
    get_async_session,
    list_pipeline_records,
    log_audit,
    store_record,
)
from stages.stage0_identity.adapters import (
    AvatarProviderAdapter,
    MockAvatarProvider,
    MockVoiceProvider,
    VoiceProviderAdapter,
)

log = structlog.get_logger(__name__)
STAGE = "stage0_identity"
CONTRACT = "IdentityMatrix"


def _voice_adapter(
    voice: VoiceProviderAdapter | None,
) -> VoiceProviderAdapter:
    return voice if voice is not None else MockVoiceProvider()


def _avatar_adapter(
    avatar: AvatarProviderAdapter | None,
) -> AvatarProviderAdapter:
    return avatar if avatar is not None else MockAvatarProvider()


async def _persist(matrix: IdentityMatrix) -> str:
    payload = matrix.model_dump(mode="json")
    record_id = await store_record(
        contract_type=CONTRACT,
        stage=STAGE,
        data=payload,
        identity_id=str(matrix.id),
    )
    return record_id


async def create_default_identity(
    voice: VoiceProviderAdapter | None = None,
    avatar: AvatarProviderAdapter | None = None,
) -> IdentityMatrix:
    settings = config.get_settings()
    va, aa = _voice_adapter(voice), _avatar_adapter(avatar)
    log.info("identity.create_default.start", dry_run=settings.dry_run)

    matrix = IdentityMatrix(
        name="Avery Bytes",
        archetype=PersonaArchetype.EDUCATOR,
        tagline="Making AI legible, one short at a time.",
        guidelines=ContentGuidelines(
            topics=["machine learning", "productivity", "creator economy"],
            tone="friendly-expert",
        ),
        platforms=[
            PlatformPresence(
                platform=Platform.TIKTOK,
                handle="averybytes_ai",
                bio="AI explainers and tool walkthroughs.",
            ),
            PlatformPresence(
                platform=Platform.YOUTUBE,
                handle="AveryBytesAI",
                bio="Short-form AI tutorials.",
            ),
        ],
    )

    voice_profile = await va.generate_voice_pack(matrix)
    avatar_profile = await aa.generate_avatar(matrix)
    matrix = matrix.model_copy(update={"voice": voice_profile, "avatar": avatar_profile})
    matrix.add_audit("identity_created", mode="default")

    await _persist(matrix)
    await log_audit(
        STAGE,
        "identity_created",
        identity_id=str(matrix.id),
        mode="default",
    )
    log.info("identity.create_default.done", identity_id=str(matrix.id))
    return matrix


async def create_identity(
    name: str,
    archetype: PersonaArchetype,
    topics: list[str],
    platforms: list[Platform],
    voice: VoiceProviderAdapter | None = None,
    avatar: AvatarProviderAdapter | None = None,
) -> IdentityMatrix:
    settings = config.get_settings()
    va, aa = _voice_adapter(voice), _avatar_adapter(avatar)
    log.info(
        "identity.create.start",
        name=name,
        archetype=archetype.value,
        dry_run=settings.dry_run,
    )

    handle_base = "".join(c for c in name.lower() if c.isalnum()) or "creator"
    platform_rows = [
        PlatformPresence(
            platform=p,
            handle=f"{handle_base}_{p.value}",
            bio=f"{name} — {p.value}",
        )
        for p in platforms
    ]

    matrix = IdentityMatrix(
        name=name,
        archetype=archetype,
        tagline=f"{name} · {archetype.value.replace('_', ' ')}",
        guidelines=ContentGuidelines(topics=list(topics)),
        platforms=platform_rows,
    )

    voice_profile = await va.generate_voice_pack(matrix)
    avatar_profile = await aa.generate_avatar(matrix)
    matrix = matrix.model_copy(update={"voice": voice_profile, "avatar": avatar_profile})
    matrix.add_audit("identity_created", name=name, archetype=archetype.value)

    await _persist(matrix)
    await log_audit(
        STAGE,
        "identity_created",
        identity_id=str(matrix.id),
        name=name,
        archetype=archetype.value,
    )
    log.info("identity.create.done", identity_id=str(matrix.id))
    return matrix


async def get_identity(identity_id: UUID) -> IdentityMatrix | None:
    session = await get_async_session()
    async with session:
        res = await session.execute(
            select(PipelineRecord).where(
                PipelineRecord.id == str(identity_id),
                PipelineRecord.contract_type == CONTRACT,
            )
        )
        row = res.scalar_one_or_none()
    if row is None:
        log.warning("identity.get.miss", identity_id=str(identity_id))
        return None
    data = json.loads(row.data)
    return IdentityMatrix.model_validate(data)


async def list_identities() -> list[IdentityMatrix]:
    rows = await list_pipeline_records(CONTRACT, STAGE, limit=500)
    out = [IdentityMatrix.model_validate(r) for r in rows]
    log.info("identity.list", count=len(out))
    return out
