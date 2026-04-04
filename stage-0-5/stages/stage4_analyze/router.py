from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from packages.contracts.analytics import RedoReason

from .adapters import MockMetricsCollector, MockPerformanceAnalyzer
from .service import AnalyzeService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analyze", tags=["stage4_analyze"])

_default_service: AnalyzeService | None = None


def get_analyze_service() -> AnalyzeService:
    global _default_service
    if _default_service is None:
        _default_service = AnalyzeService(MockMetricsCollector(), MockPerformanceAnalyzer())
        logger.info("analyze_service_initialized")
    return _default_service


ServiceDep = Annotated[AnalyzeService, Depends(get_analyze_service)]


class RedoRequest(BaseModel):
    identity_id: str
    content_id: str = ""
    reason: RedoReason
    target_stage: int = Field(ge=1, le=3)


@router.post("/collect/{distribution_record_id}")
async def collect_metrics_endpoint(
    distribution_record_id: str,
    svc: ServiceDep,
) -> list[dict[str, Any]]:
    metrics = await svc.collect_metrics(distribution_record_id)
    return [m.model_dump(mode="json") for m in metrics]


@router.post("/performance/{identity_id}")
async def analyze_performance_endpoint(
    identity_id: str,
    svc: ServiceDep,
    window_hours: float = Query(default=24.0, ge=0.1, le=168.0),
) -> dict[str, Any]:
    return await svc.analyze_performance(identity_id, window_hours=window_hours)


@router.post("/optimize/{identity_id}")
async def generate_optimization_endpoint(
    identity_id: str,
    svc: ServiceDep,
) -> dict[str, Any]:
    envelope = await svc.generate_optimization(identity_id)
    return envelope.model_dump(mode="json")


@router.post("/redo")
async def queue_redo_endpoint(body: RedoRequest, svc: ServiceDep) -> dict[str, Any]:
    item = await svc.queue_redo(
        body.identity_id,
        body.content_id,
        body.reason,
        body.target_stage,
    )
    return item.model_dump(mode="json")


@router.get("/metrics")
async def list_metrics_endpoint(
    svc: ServiceDep,
    identity_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    metrics = await svc.list_stored_metrics(identity_id=identity_id)
    return [m.model_dump(mode="json") for m in metrics]


@router.get("/directives")
async def list_directives_endpoint(
    svc: ServiceDep,
    identity_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    directives = await svc.list_stored_directives(identity_id=identity_id)
    return [d.model_dump(mode="json") for d in directives]
