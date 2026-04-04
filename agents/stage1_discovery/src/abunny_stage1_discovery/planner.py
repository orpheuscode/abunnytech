from __future__ import annotations

import uuid

from pipeline_contracts.models import IdentityMatrix
from pipeline_contracts.models.directives import OptimizationDirectiveEnvelope

from abunny_stage1_discovery.models import ContentTierDemand, DiscoveryPlan


def _platform_labels(identity: IdentityMatrix) -> list[str]:
    return [p.value for p in identity.platform_targets]


def _directives_for_stage1(
    directives: list[OptimizationDirectiveEnvelope] | None,
) -> tuple[list[str], list[str]]:
    """Return (notes, extra_queries) from envelopes targeting stage1."""
    notes: list[str] = []
    extra_queries: list[str] = []
    if not directives:
        return notes, extra_queries
    for d in directives:
        if "stage1" not in d.target_stages:
            continue
        if d.rationale:
            notes.append(d.rationale)
        payload = d.envelope.payload
        if isinstance(payload, dict):
            q = payload.get("extra_queries") or payload.get("seed_queries")
            if isinstance(q, list):
                extra_queries.extend(str(x) for x in q)
            single = payload.get("focus_query")
            if isinstance(single, str) and single.strip():
                extra_queries.append(single.strip())
    return notes, extra_queries


def plan_discovery(
    identity: IdentityMatrix,
    tier_demand: ContentTierDemand,
    directives: list[OptimizationDirectiveEnvelope] | None = None,
    *,
    plan_id: str | None = None,
    default_max_candidates: int = 12,
) -> DiscoveryPlan:
    platforms = _platform_labels(identity)
    seed_queries = [
        f"{identity.niche} tips",
        f"{identity.niche} tutorial short",
        f"learn {identity.niche} fast",
    ]
    for t in identity.persona.topics[:5]:
        seed_queries.append(f"{identity.niche} {t}")

    dir_notes, extra_q = _directives_for_stage1(directives)
    seed_queries.extend(extra_q)

    tier_targets = dict(tier_demand.tiers)
    total_demand = sum(tier_targets.values())
    base = total_demand if total_demand > 0 else default_max_candidates
    max_candidates = min(500, max(base, 4))

    return DiscoveryPlan(
        plan_id=plan_id or f"dp_{uuid.uuid4().hex[:10]}",
        matrix_id=identity.matrix_id,
        niche=identity.niche,
        platforms=platforms,
        seed_queries=list(dict.fromkeys(seed_queries)),
        seed_handles=[],
        max_candidates=min(max_candidates, 500),
        tier_targets=tier_targets,
        directive_notes=dir_notes,
    )
