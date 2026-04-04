from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from packages.contracts.base import Platform
from packages.shared.feature_flags import is_enabled

from .models import ApprovalAction, ApprovalStatus
from .service import FEATURE_DISABLED_MESSAGE, monetize_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/monetize", tags=["stage5-monetize"])


def require_stage5_monetize() -> None:
    if not is_enabled("stage5_monetize"):
        log.info("stage5_monetize.http_blocked", reason="feature_disabled")
        raise HTTPException(status_code=403, detail=FEATURE_DISABLED_MESSAGE)


FlagDep = Depends(require_stage5_monetize)


def _raise_if_not_ok(result: dict) -> dict:
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "Operation failed."))
    return result


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ProductCreateRequest(BaseModel):
    identity_id: str
    name: str
    price: float = 0.0
    description: str = ""
    currency: str = "USD"
    affiliate_url: str = ""
    category: str = ""
    active: bool = True


class CatalogIngestRequest(BaseModel):
    source_url: str
    identity_id: str


class ScoreProductRequest(BaseModel):
    product_id: str
    identity_id: str


class ListingDraftRequest(BaseModel):
    product_id: str
    identity_id: str


class OutreachCreateRequest(BaseModel):
    identity_id: str
    brand_name: str
    platform: Platform


class OutreachDraftRequest(BaseModel):
    outreach_id: str
    identity_id: str
    identity_name: str = "Creator"


class DMLogRequest(BaseModel):
    identity_id: str
    platform: Platform
    handle: str = Field(..., description="Counterparty social handle")
    message: str


class AttributionRequest(BaseModel):
    identity_id: str
    product_id: str


class ApprovalCreateRequest(BaseModel):
    identity_id: str
    action: ApprovalAction
    target_id: str
    description: str = ""


class ApprovalReviewRequest(BaseModel):
    approval_id: str
    reviewer: str
    approved: bool
    notes: str = ""


# ---------------------------------------------------------------------------
# Product catalog
# ---------------------------------------------------------------------------

@router.post("/products", dependencies=[FlagDep])
async def add_product(body: ProductCreateRequest) -> dict:
    result = await monetize_service.add_product(
        body.identity_id, body.name, body.price,
        description=body.description, currency=body.currency,
        affiliate_url=body.affiliate_url, category=body.category,
        active=body.active,
    )
    return _raise_if_not_ok(result)


@router.get("/products", dependencies=[FlagDep])
async def list_products(identity_id: str | None = Query(None)) -> dict:
    result = await monetize_service.list_products(identity_id=identity_id)
    return _raise_if_not_ok(result)


@router.post("/products/ingest", dependencies=[FlagDep])
async def ingest_catalog(body: CatalogIngestRequest) -> dict:
    result = await monetize_service.ingest_catalog(body.source_url, body.identity_id)
    return _raise_if_not_ok(result)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@router.post("/products/score", dependencies=[FlagDep])
async def score_product(body: ScoreProductRequest) -> dict:
    result = await monetize_service.score_product(body.product_id, body.identity_id)
    return _raise_if_not_ok(result)


@router.post("/products/score-all", dependencies=[FlagDep])
async def score_all_products(identity_id: str = Query(...)) -> dict:
    result = await monetize_service.score_all_products(identity_id)
    return _raise_if_not_ok(result)


# ---------------------------------------------------------------------------
# Listing drafts
# ---------------------------------------------------------------------------

@router.post("/listings/draft", dependencies=[FlagDep])
async def create_listing_draft(body: ListingDraftRequest) -> dict:
    result = await monetize_service.create_listing_draft(body.product_id, body.identity_id)
    return _raise_if_not_ok(result)


@router.get("/listings/drafts", dependencies=[FlagDep])
async def list_listing_drafts(identity_id: str | None = Query(None)) -> dict:
    result = await monetize_service.list_listing_drafts(identity_id=identity_id)
    return _raise_if_not_ok(result)


# ---------------------------------------------------------------------------
# Brand outreach
# ---------------------------------------------------------------------------

@router.post("/outreach", dependencies=[FlagDep])
async def create_outreach(body: OutreachCreateRequest) -> dict:
    result = await monetize_service.create_outreach(
        body.identity_id, body.brand_name, body.platform,
    )
    return _raise_if_not_ok(result)


@router.get("/outreach", dependencies=[FlagDep])
async def list_outreach(identity_id: str | None = Query(None)) -> dict:
    result = await monetize_service.list_outreach(identity_id=identity_id)
    return _raise_if_not_ok(result)


@router.post("/outreach/draft", dependencies=[FlagDep])
async def generate_outreach_draft(body: OutreachDraftRequest) -> dict:
    result = await monetize_service.generate_outreach_draft(
        body.outreach_id, body.identity_id, body.identity_name,
    )
    return _raise_if_not_ok(result)


@router.get("/outreach/drafts", dependencies=[FlagDep])
async def list_outreach_drafts(identity_id: str | None = Query(None)) -> dict:
    result = await monetize_service.list_outreach_drafts(identity_id=identity_id)
    return _raise_if_not_ok(result)


# ---------------------------------------------------------------------------
# DM logging
# ---------------------------------------------------------------------------

@router.post("/dm", dependencies=[FlagDep])
async def log_dm(body: DMLogRequest) -> dict:
    result = await monetize_service.log_dm(
        body.identity_id, body.platform, body.handle, body.message,
    )
    return _raise_if_not_ok(result)


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

@router.post("/attribution", dependencies=[FlagDep])
async def compute_attribution(body: AttributionRequest) -> dict:
    result = await monetize_service.compute_attribution(body.identity_id, body.product_id)
    return _raise_if_not_ok(result)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@router.post("/approvals", dependencies=[FlagDep])
async def request_approval(body: ApprovalCreateRequest) -> dict:
    result = await monetize_service.request_approval(
        body.identity_id, body.action, body.target_id, body.description,
    )
    return _raise_if_not_ok(result)


@router.post("/approvals/review", dependencies=[FlagDep])
async def review_approval(body: ApprovalReviewRequest) -> dict:
    result = await monetize_service.review_approval(
        body.approval_id, body.reviewer, body.approved, body.notes,
    )
    return _raise_if_not_ok(result)


@router.get("/approvals", dependencies=[FlagDep])
async def list_approvals(
    identity_id: str | None = Query(None),
    status: ApprovalStatus | None = Query(None),
) -> dict:
    result = await monetize_service.list_approvals(
        identity_id=identity_id, status_filter=status,
    )
    return _raise_if_not_ok(result)
