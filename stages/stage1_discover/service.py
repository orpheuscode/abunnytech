from __future__ import annotations

import structlog

from packages.contracts.base import Platform
from packages.contracts.discovery import (
    CompetitorWatchItem,
    TrainingMaterial,
    TrainingMaterialsManifest,
    TrendingAudioItem,
)
from packages.shared.db import list_pipeline_records, log_audit, store_record
from stages.stage1_discover.adapters import (
    CompetitorAnalysisAdapter,
    MockCompetitorAnalysis,
    MockTrendDiscovery,
    TrendDiscoveryAdapter,
)

STAGE = "stage1_discover"
CONTRACT_TRENDING = "TrendingAudioItem"
CONTRACT_COMPETITOR = "CompetitorWatchItem"
CONTRACT_MANIFEST = "TrainingMaterialsManifest"

log = structlog.get_logger(__name__)


class DiscoveryService:
    def __init__(
        self,
        *,
        trends: TrendDiscoveryAdapter | None = None,
        competitors: CompetitorAnalysisAdapter | None = None,
        default_trend_count: int = 10,
    ) -> None:
        self._trends = trends or MockTrendDiscovery()
        self._competitors = competitors or MockCompetitorAnalysis()
        self._default_trend_count = default_trend_count

    async def discover_trending(self, platform: Platform, identity_id: str) -> list[TrendingAudioItem]:
        log.info("discover_trending", platform=platform.value, identity_id=identity_id)
        await log_audit(
            STAGE,
            "discover_trending_started",
            identity_id=identity_id,
            platform=platform.value,
        )
        items = await self._trends.fetch_trending(platform, self._default_trend_count)
        for item in items:
            payload = item.model_dump(mode="json")
            await store_record(CONTRACT_TRENDING, STAGE, payload, identity_id=identity_id)
        await log_audit(
            STAGE,
            "discover_trending_finished",
            identity_id=identity_id,
            platform=platform.value,
            count=len(items),
        )
        return items

    async def analyze_competitors(
        self,
        platform: Platform,
        handles: list[str],
        identity_id: str,
    ) -> list[CompetitorWatchItem]:
        log.info(
            "analyze_competitors",
            platform=platform.value,
            identity_id=identity_id,
            handle_count=len(handles),
        )
        await log_audit(
            STAGE,
            "analyze_competitors_started",
            identity_id=identity_id,
            platform=platform.value,
            handles=handles,
        )
        results: list[CompetitorWatchItem] = []
        for raw in handles:
            handle = raw.strip()
            if not handle:
                continue
            item = await self._competitors.analyze(platform, handle)
            await store_record(
                CONTRACT_COMPETITOR,
                STAGE,
                item.model_dump(mode="json"),
                identity_id=identity_id,
            )
            results.append(item)
        await log_audit(
            STAGE,
            "analyze_competitors_finished",
            identity_id=identity_id,
            platform=platform.value,
            count=len(results),
        )
        return results

    async def build_training_manifest(
        self,
        identity_id: str,
        materials: list[TrainingMaterial],
    ) -> TrainingMaterialsManifest:
        log.info("build_training_manifest", identity_id=identity_id, material_count=len(materials))
        await log_audit(
            STAGE,
            "build_training_manifest_started",
            identity_id=identity_id,
            material_count=len(materials),
        )
        tag_set: list[str] = []
        for m in materials:
            tag_set.extend(m.tags)
        recommended_topics = sorted({t.lower().strip() for t in tag_set if t.strip()})[:12]
        manifest = TrainingMaterialsManifest(
            identity_id=identity_id,
            materials=materials,
            analysis_summary=f"Collected {len(materials)} reference clips for style/topic conditioning.",
            recommended_styles=["punchy hooks", "authentic B-roll", "on-screen captions"],
            recommended_topics=recommended_topics or ["general audience growth"],
        )
        await store_record(
            CONTRACT_MANIFEST,
            STAGE,
            manifest.model_dump(mode="json"),
            identity_id=identity_id,
        )
        await log_audit(
            STAGE,
            "build_training_manifest_finished",
            identity_id=identity_id,
            material_count=len(materials),
        )
        return manifest

    async def list_stored_trending(
        self,
        *,
        identity_id: str | None = None,
        limit: int = 50,
    ) -> list[TrendingAudioItem]:
        rows = await list_pipeline_records(
            CONTRACT_TRENDING,
            STAGE,
            identity_id=identity_id,
            limit=limit,
        )
        return [TrendingAudioItem.model_validate(r) for r in rows]


_default_service: DiscoveryService | None = None


def get_discovery_service() -> DiscoveryService:
    global _default_service
    if _default_service is None:
        _default_service = DiscoveryService()
    return _default_service
