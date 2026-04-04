from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from apps.api.deps import get_audit, get_repo, get_settings_dep
from apps.api.schemas import Stage0Body
from pipeline_core.repository import RunRepository
from pipeline_core.settings import Settings
from pipeline_stage0_identity import IdentityStageInput, run_stage0
from pipeline_stage1_discover import MockDiscoveryProvider, run_stage1
from pipeline_stage2_generate import FixtureVideoRenderProvider, run_stage2

app = FastAPI(title="Creator Pipeline API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/settings")
def settings_view(settings: Annotated[Settings, Depends(get_settings_dep)]) -> dict[str, bool]:
    return {
        "dry_run": settings.dry_run,
        "feature_stage5_enabled": settings.feature_stage5_enabled,
        "disclosure_demo": settings.disclosure_demo,
    }


@app.post("/runs")
def create_run(
    repo: Annotated[RunRepository, Depends(get_repo)],
    run_id: str | None = Query(default=None, description="Optional client-supplied run id"),
) -> dict[str, str]:
    rid = repo.create_run(run_id)
    return {"run_id": rid}


@app.post("/runs/{run_id}/stage0")
def post_stage0(
    run_id: str,
    body: Stage0Body,
    repo: Annotated[RunRepository, Depends(get_repo)],
    audit: Annotated[Any, Depends(get_audit)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> JSONResponse:
    inp = IdentityStageInput(
        display_name=body.display_name,
        niche=body.niche,
        tone=body.tone,
        topics=body.topics,
    )
    identity, manifest = run_stage0(run_id, inp, repo, audit, settings)
    return JSONResponse(
        {
            "identity_matrix": identity.model_dump(mode="json"),
            "training_materials_manifest": manifest.model_dump(mode="json"),
        }
    )


@app.post("/runs/{run_id}/stage1")
def post_stage1(
    run_id: str,
    repo: Annotated[RunRepository, Depends(get_repo)],
    audit: Annotated[Any, Depends(get_audit)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> JSONResponse:
    try:
        blueprint = run_stage1(run_id, repo, audit, settings, MockDiscoveryProvider())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return JSONResponse({"video_blueprint": blueprint.model_dump(mode="json")})


@app.post("/runs/{run_id}/stage2")
def post_stage2(
    run_id: str,
    repo: Annotated[RunRepository, Depends(get_repo)],
    audit: Annotated[Any, Depends(get_audit)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> JSONResponse:
    try:
        package = run_stage2(
            run_id,
            repo,
            audit,
            settings,
            FixtureVideoRenderProvider(),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return JSONResponse({"content_package": package.model_dump(mode="json")})


@app.get("/runs/{run_id}/artifacts")
def get_artifacts(
    run_id: str,
    repo: Annotated[RunRepository, Depends(get_repo)],
) -> dict[str, Any]:
    if not repo.run_exists(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    return repo.get_all_artifacts(run_id)
