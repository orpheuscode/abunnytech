"""Pipeline runner that executes stages 0-4 using the state layer."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from orchestrator.context import PipelineContext
from packages.state.models import (
    ContentPackage,
    DistributionRecord,
    IdentityMatrix,
    OptimizationDirectiveEnvelope,
    PersonaArchetype,
    Platform,
    PlatformPresence,
    RedoQueueItem,
    TrendingAudioItem,
    VideoBlueprint,
)
from packages.state.registry import RepositoryRegistry
from packages.state.sqlite import Database


async def _run(identity_name: str, dry_run: bool) -> dict:
    db = Database(":memory:")
    await db.connect()
    registry = RepositoryRegistry(db)

    for repo in registry.all_repos().values():
        await repo._ensure_table()

    ctx = PipelineContext(identity_id=uuid4())
    results: dict[str, object] = {"dry_run": dry_run, "stages": {}}

    # Stage 0 – Identity
    identity = IdentityMatrix(
        id=ctx.identity_id,
        name=identity_name,
        archetype=PersonaArchetype.EDUCATOR,
        tagline=f"{identity_name} – AI creator persona",
        platforms=[PlatformPresence(platform=Platform.TIKTOK, handle=f"@{identity_name.lower().replace(' ', '_')}")],
    )
    await registry.identity_matrix.create(identity)
    ctx.set_result("identity", str(identity.id))
    results["stages"]["stage0_identity"] = {"identity_id": str(identity.id), "name": identity.name}
    ctx.advance()

    # Stage 1 – Discovery (mock)
    audio = TrendingAudioItem(
        platform=Platform.TIKTOK,
        audio_id="mock_audio_001",
        title="Trending Beat",
        artist="DemoArtist",
        usage_count=100_000,
        trend_score=0.88,
    )
    await registry.trending_audio.create(audio)
    ctx.set_result("trending_audio_id", str(audio.id))
    results["stages"]["stage1_discover"] = {"audio_id": str(audio.id), "title": audio.title}
    ctx.advance()

    # Stage 2 – Content Generation (mock)
    blueprint = VideoBlueprint(
        identity_id=identity.id,
        title=f"Quick take: {audio.title}",
        script="Hook → Body → CTA",
        audio_id=audio.audio_id,
        duration_seconds=30,
        status="approved",
    )
    await registry.video_blueprints.create(blueprint)

    package = ContentPackage(
        blueprint_id=blueprint.id,
        identity_id=identity.id,
        video_url="https://cdn.example.com/mock.mp4",
        caption="Demo content package",
        hashtags=["#demo", "#ai"],
        platform=Platform.TIKTOK,
        status="ready",
    )
    await registry.content_packages.create(package)
    ctx.set_result("package_id", str(package.id))
    results["stages"]["stage2_generate"] = {"blueprint_id": str(blueprint.id), "package_id": str(package.id)}
    ctx.advance()

    # Stage 3 – Distribution (mock / dry-run)
    dist = DistributionRecord(
        content_package_id=package.id,
        platform=Platform.TIKTOK,
        status="dry_run" if dry_run else "posted",
        post_url="" if dry_run else "https://tiktok.com/@demo/video/mock",
    )
    await registry.distribution_records.create(dist)
    ctx.set_result("distribution_id", str(dist.id))
    results["stages"]["stage3_distribute"] = {"distribution_id": str(dist.id), "status": dist.status}
    ctx.advance()

    # Stage 4 – Analytics (mock)
    directive = OptimizationDirectiveEnvelope(
        identity_id=identity.id,
        directives=[{"type": "shorten_intro", "target_seconds": 3}],
    )
    await registry.optimization_directives.create(directive)

    redo = RedoQueueItem(
        content_package_id=package.id,
        reason="Low retention in first 3s",
        priority=1,
        status="pending",
    )
    await registry.redo_queue.create(redo)
    results["stages"]["stage4_analyze"] = {
        "directive_id": str(directive.id),
        "redo_id": str(redo.id),
    }

    await db.disconnect()
    return results


def run_pipeline(identity_name: str = "Demo Creator", *, dry_run: bool = True) -> dict:
    """Synchronous entry-point that runs the async pipeline."""
    return asyncio.run(_run(identity_name, dry_run))
