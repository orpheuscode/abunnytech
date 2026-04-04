"""FastAPI routes for Stage 2 generate/render."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from packages.contracts.base import Platform
from stages.stage2_generate.service import ContentGenerationService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/generate", tags=["generate"])


def get_generation_service() -> ContentGenerationService:
    return ContentGenerationService()


ServiceDep = Annotated[ContentGenerationService, Depends(get_generation_service)]


class BlueprintCreateRequest(BaseModel):
    identity_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    platform: Platform = Platform.TIKTOK
    scene_count: int = Field(default=7, ge=3, le=12)


@router.post("/blueprint")
async def create_blueprint(
    body: BlueprintCreateRequest,
    svc: ServiceDep,
):
    log.info("api_blueprint_create", title=body.title)
    blueprint = await svc.create_blueprint(
        body.identity_id,
        body.title,
        body.topic,
        body.platform,
        scene_count=body.scene_count,
    )
    return blueprint.model_dump(mode="json")


@router.post("/render/{blueprint_id}")
async def render_blueprint(blueprint_id: str, svc: ServiceDep):
    log.info("api_render", blueprint_id=blueprint_id)
    try:
        package = await svc.render_content(blueprint_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return package.model_dump(mode="json")


@router.get("/blueprints")
async def list_blueprints(svc: ServiceDep):
    blueprints = await svc.list_blueprints()
    return [b.model_dump(mode="json") for b in blueprints]


@router.get("/packages")
async def list_packages(svc: ServiceDep):
    packages = await svc.list_packages()
    return [p.model_dump(mode="json") for p in packages]
