from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from packages.contracts.base import Platform
from packages.contracts.distribution import DistributionRecord
from stages.stage3_distribute.service import DistributionService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/distribute", tags=["distribute"])


def get_distribution_service() -> DistributionService:
    return DistributionService()


class PostContentRequest(BaseModel):
    content_package_id: str = Field(..., min_length=1)
    platform: Platform
    dry_run: bool = True


class ReplyCommentsRequest(BaseModel):
    distribution_record_id: str = Field(..., min_length=1)
    identity_id: str = Field(..., min_length=1)


class ReplyCommentsResponse(BaseModel):
    distribution_record_id: str
    identity_id: str
    replies: list[str]


@router.post("/post", response_model=DistributionRecord)
async def post_content(
    body: PostContentRequest,
    svc: Annotated[DistributionService, Depends(get_distribution_service)],
) -> DistributionRecord:
    log.info(
        "api_distribute_post",
        content_package_id=body.content_package_id,
        platform=body.platform.value,
        dry_run=body.dry_run,
    )
    return await svc.post_content(body.content_package_id, body.platform, dry_run=body.dry_run)


@router.post("/reply", response_model=ReplyCommentsResponse)
async def reply_to_comments(
    body: ReplyCommentsRequest,
    svc: Annotated[DistributionService, Depends(get_distribution_service)],
) -> ReplyCommentsResponse:
    log.info(
        "api_distribute_reply",
        distribution_record_id=body.distribution_record_id,
        identity_id=body.identity_id,
    )
    if await svc.get_distribution_status(body.distribution_record_id) is None:
        raise HTTPException(status_code=404, detail="Distribution record not found")
    replies = await svc.reply_to_comments(body.distribution_record_id, body.identity_id)
    return ReplyCommentsResponse(
        distribution_record_id=body.distribution_record_id,
        identity_id=body.identity_id,
        replies=replies,
    )


@router.get("/records", response_model=list[DistributionRecord])
async def list_distribution_records(
    svc: Annotated[DistributionService, Depends(get_distribution_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DistributionRecord]:
    return await svc.list_distribution_records(limit=limit)


@router.get("/records/{record_id}", response_model=DistributionRecord)
async def get_distribution_record(
    record_id: str,
    svc: Annotated[DistributionService, Depends(get_distribution_service)],
) -> DistributionRecord:
    record = await svc.get_distribution_status(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Distribution record not found")
    return record
