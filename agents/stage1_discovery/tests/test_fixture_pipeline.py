from __future__ import annotations

from pathlib import Path

import pytest
from pipeline_contracts.models import VideoBlueprint

from abunny_stage1_discovery.models import ContentTierDemand
from abunny_stage1_discovery.pipeline import load_identity_fixture, run_stage1_fixture_pipeline


@pytest.fixture
def fixture_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "examples" / "stage1" / "fixtures"


def test_fixture_pipeline_emits_valid_blueprints(fixture_dir: Path) -> None:
    identity = load_identity_fixture(fixture_dir)
    result = run_stage1_fixture_pipeline(
        fixture_dir,
        identity,
        tier_demand=ContentTierDemand(tiers={"viral": 2, "standard": 1}),
    )
    assert len(result.blueprints) == 3
    for bp in result.blueprints:
        VideoBlueprint.model_validate(bp.model_dump(mode="json"))
    assert len(result.ranked_queue) == 3
    assert result.ranked_queue[0].rank == 1
    ids = {q.candidate_id for q in result.ranked_queue}
    assert "cand_std_d" not in ids
    art = result.to_artifacts()
    assert len(art.video_blueprints) == 3
    assert len(art.trending_audio) >= 1
    assert len(art.competitor_watchlist) >= 1


def test_artifacts_round_trip_through_video_blueprint(fixture_dir: Path) -> None:
    identity = load_identity_fixture(fixture_dir)
    result = run_stage1_fixture_pipeline(fixture_dir, identity, tier_demand=ContentTierDemand())
    for row in result.to_artifacts().video_blueprints:
        VideoBlueprint.model_validate(row)
