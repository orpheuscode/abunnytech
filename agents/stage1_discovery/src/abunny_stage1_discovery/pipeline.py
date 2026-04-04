from __future__ import annotations

from pathlib import Path

from pipeline_contracts.models import IdentityMatrix
from pipeline_contracts.models.directives import OptimizationDirectiveEnvelope

from abunny_stage1_discovery.adapters.fixture_adapters import (
    FixtureAccountMetadata,
    FixtureAnalysisPipeline,
    FixtureMediaDownloadPlanner,
    FixtureResearchCatalog,
    FixtureShortFormDiscovery,
    load_fixture_json,
)
from abunny_stage1_discovery.blueprint_builder import build_video_blueprint
from abunny_stage1_discovery.models import ContentTierDemand, RankedQueueItem, Stage1RunResult
from abunny_stage1_discovery.planner import plan_discovery
from abunny_stage1_discovery.scoring import copyability_score, prioritize_for_tiers


def run_stage1_fixture_pipeline(
    fixture_dir: Path,
    identity: IdentityMatrix,
    *,
    tier_demand: ContentTierDemand | None = None,
    directives: list[OptimizationDirectiveEnvelope] | None = None,
) -> Stage1RunResult:
    """End-to-end Stage 1 using on-disk fixtures (no browser, no live ML APIs)."""
    td = tier_demand or ContentTierDemand()
    plan = plan_discovery(identity, td, directives)

    discovery = FixtureShortFormDiscovery(fixture_dir)
    account_meta = FixtureAccountMetadata(fixture_dir)
    download_planner = FixtureMediaDownloadPlanner()
    analysis = FixtureAnalysisPipeline(fixture_dir)
    catalog = FixtureResearchCatalog(fixture_dir)

    raw_list = discovery.discover_short_form(plan)
    for c in raw_list:
        if c.creator_handle:
            account_meta.extract_account_metadata(c.creator_handle, c.platform)

    all_jobs = download_planner.plan_media_downloads(raw_list)
    jobs_by_cand: dict[str, list] = {}
    for j in all_jobs:
        jobs_by_cand.setdefault(j.candidate_id, []).append(j)

    analyzed_list = []
    for c in raw_list:
        jobs = jobs_by_cand.get(c.candidate_id, [])
        analyzed_list.append(analysis.analyze(c, jobs))

    scored = [(a, *copyability_score(a)) for a in analyzed_list]
    tier_sum = sum(plan.tier_targets.values())
    if plan.tier_targets:
        output_cap = min(plan.max_candidates, tier_sum)
    else:
        output_cap = plan.max_candidates
    picked = prioritize_for_tiers(
        scored,
        plan.tier_targets,
        max_total=output_cap,
    )

    trending = catalog.load_trending_audio()
    competitors = catalog.load_competitors()

    blueprints = []
    ranked: list[RankedQueueItem] = []
    for i, row in enumerate(picked):
        a, sc, br = row
        audio_id = None
        if trending:
            audio_id = trending[i % len(trending)].audio_id
        bp = build_video_blueprint(a, identity, audio_id=audio_id)
        blueprints.append(bp)
        ranked.append(
            RankedQueueItem(
                rank=i + 1,
                blueprint_id=bp.blueprint_id,
                copyability_score=sc,
                content_tier=a.raw.content_tier,
                candidate_id=a.raw.candidate_id,
                score_breakdown=br,
            )
        )

    return Stage1RunResult(
        blueprints=blueprints,
        trending_audio=trending,
        competitor_watchlist=competitors,
        ranked_queue=ranked,
        plan=plan,
    )


def load_identity_fixture(fixture_dir: Path) -> IdentityMatrix:
    raw = load_fixture_json(fixture_dir / "identity_matrix.json")
    return IdentityMatrix.model_validate(raw)
