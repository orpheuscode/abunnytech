from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline_contracts.models.directives import OptimizationDirectiveEnvelope

from abunny_stage1_discovery.models import ContentTierDemand
from abunny_stage1_discovery.pipeline import load_identity_fixture, run_stage1_fixture_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1 dry-run using examples/stage1 fixtures.")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=None,
        help="Fixture directory (default: examples/stage1/fixtures next to repo root).",
    )
    parser.add_argument("--json", action="store_true", help="Print Stage1Artifacts JSON to stdout.")
    args = parser.parse_args()

    fixture_dir = args.fixtures
    if fixture_dir is None:
        cwd = Path.cwd()
        candidate = cwd / "examples" / "stage1" / "fixtures"
        repo_root = Path(__file__).resolve().parents[4]
        fixture_dir = candidate if candidate.is_dir() else repo_root / "examples" / "stage1" / "fixtures"

    if not fixture_dir.is_dir():
        print(f"Fixture directory not found: {fixture_dir}", file=sys.stderr)
        sys.exit(1)

    identity = load_identity_fixture(fixture_dir)
    directives_path = fixture_dir / "optimization_directives.json"
    directives: list[OptimizationDirectiveEnvelope] = []
    if directives_path.exists():
        raw_list = json.loads(directives_path.read_text(encoding="utf-8"))
        if isinstance(raw_list, list):
            directives = [OptimizationDirectiveEnvelope.model_validate(x) for x in raw_list]

    tier_path = fixture_dir / "content_tier_demand.json"
    tier_demand = ContentTierDemand()
    if tier_path.exists():
        raw_td = json.loads(tier_path.read_text(encoding="utf-8"))
        if isinstance(raw_td, dict) and "tiers" in raw_td:
            tier_demand = ContentTierDemand.model_validate(raw_td)
        elif isinstance(raw_td, dict):
            tier_demand = ContentTierDemand(tiers={str(k): int(v) for k, v in raw_td.items()})

    result = run_stage1_fixture_pipeline(
        fixture_dir,
        identity,
        tier_demand=tier_demand,
        directives=directives or None,
    )
    artifacts = result.to_artifacts()
    if args.json:
        print(json.dumps(artifacts.model_dump(mode="json"), indent=2))
    else:
        print(f"Plan: {result.plan.plan_id} ({len(result.blueprints)} blueprints)")
        for bp in result.blueprints:
            print(f"  - {bp.blueprint_id} | {bp.title[:60]!r}")


if __name__ == "__main__":
    main()
