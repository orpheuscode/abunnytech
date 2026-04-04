from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from packages.contracts.base import Platform
from packages.contracts.identity import IdentityMatrix, PersonaArchetype
from stages.stage0_identity import service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/identity", tags=["identity"])


class CreateIdentityRequest(BaseModel):
    name: str
    archetype: PersonaArchetype
    topics: list[str] = Field(default_factory=list)
    platforms: list[Platform] = Field(default_factory=list)


@router.post("", response_model=IdentityMatrix, status_code=status.HTTP_201_CREATED)
async def create_identity_endpoint(body: CreateIdentityRequest) -> IdentityMatrix:
    log.info("http.identity.create", name=body.name)
    return await service.create_identity(
        name=body.name,
        archetype=body.archetype,
        topics=body.topics,
        platforms=body.platforms,
    )


@router.post("/default", response_model=IdentityMatrix, status_code=status.HTTP_201_CREATED)
async def create_default_identity_endpoint() -> IdentityMatrix:
    log.info("http.identity.create_default")
    return await service.create_default_identity()


@router.get("", response_model=list[IdentityMatrix])
async def list_identities_endpoint() -> list[IdentityMatrix]:
    return await service.list_identities()


@router.get("/{identity_id}", response_model=IdentityMatrix)
async def get_identity_endpoint(identity_id: UUID) -> IdentityMatrix:
    found = await service.get_identity(identity_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")
    return found
