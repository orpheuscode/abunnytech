from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from packages.contracts.base import Platform
from packages.contracts.discovery import (
    CompetitorWatchItem,
    TrainingMaterial,
    TrainingMaterialsManifest,
    TrendingAudioItem,
)
from stages.stage1_discover.service import DiscoveryService, get_discovery_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/discover", tags=["stage1-discover"])


class TrendingDiscoverRequest(BaseModel):
    platform: Platform
    identity_id: str = Field(min_length=1)


class CompetitorsAnalyzeRequest(BaseModel):
    platform: Platform
    handles: list[str] = Field(min_length=1)
    identity_id: str = Field(min_length=1)


class TrainingManifestRequest(BaseModel):
    identity_id: str = Field(min_length=1)
    materials: list[TrainingMaterial] = Field(default_factory=list)


@router.post("/trending", response_model=list[TrendingAudioItem])
async def post_discover_trending(
    body: TrendingDiscoverRequest,
    svc: Annotated[DiscoveryService, Depends(get_discovery_service)],
) -> list[TrendingAudioItem]:
    log.info("api_discover_trending", identity_id=body.identity_id, platform=body.platform.value)
    return await svc.discover_trending(body.platform, body.identity_id)


@router.post("/competitors", response_model=list[CompetitorWatchItem])
async def post_analyze_competitors(
    body: CompetitorsAnalyzeRequest,
    svc: Annotated[DiscoveryService, Depends(get_discovery_service)],
) -> list[CompetitorWatchItem]:
    log.info(
        "api_analyze_competitors",
        identity_id=body.identity_id,
        platform=body.platform.value,
    )
    return await svc.analyze_competitors(body.platform, body.handles, body.identity_id)


@router.post("/training-manifest", response_model=TrainingMaterialsManifest)
async def post_training_manifest(
    body: TrainingManifestRequest,
    svc: Annotated[DiscoveryService, Depends(get_discovery_service)],
) -> TrainingMaterialsManifest:
    log.info("api_training_manifest", identity_id=body.identity_id)
    return await svc.build_training_manifest(body.identity_id, body.materials)


@router.get("/trending", response_model=list[TrendingAudioItem])
async def get_discovered_trending(
    svc: Annotated[DiscoveryService, Depends(get_discovery_service)],
    identity_id: str | None = Query(default=None, description="Filter to one creator identity"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[TrendingAudioItem]:
    log.info("api_list_trending", identity_id=identity_id, limit=limit)
    return await svc.list_stored_trending(identity_id=identity_id, limit=limit)
