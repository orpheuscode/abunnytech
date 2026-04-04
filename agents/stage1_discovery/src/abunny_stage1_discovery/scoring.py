from __future__ import annotations

from abunny_stage1_discovery.analysis_enums import CtaKind, HookLabel, ProductIntegration
from abunny_stage1_discovery.models import AnalyzedCandidate


def copyability_score(candidate: AnalyzedCandidate) -> tuple[float, dict[str, float]]:
    """Heuristic 0..1 score: easier-to-remix shorts rank higher."""
    breakdown: dict[str, float] = {}
    score = 0.35

    if candidate.transcript:
        breakdown["transcript"] = 0.2
        score += 0.2

    hook = candidate.hook_label
    if hook in (HookLabel.PATTERN_INTERRUPT.value, HookLabel.CURIOSITY_GAP.value):
        breakdown["hook_strength"] = 0.15
        score += 0.15
    elif hook in (HookLabel.STORY.value, HookLabel.LISTICLE.value, HookLabel.TUTORIAL.value):
        breakdown["hook_strength"] = 0.08
        score += 0.08

    if candidate.overlay_cut_points:
        breakdown["structure"] = min(0.12, 0.03 * len(candidate.overlay_cut_points))
        score += breakdown["structure"]

    cta = candidate.cta_kind
    if cta == CtaKind.SOFT.value:
        breakdown["cta"] = 0.05
        score += 0.05
    elif cta in (CtaKind.HARD.value, CtaKind.LINK_IN_BIO.value):
        breakdown["cta"] = 0.02
        score += 0.02

    prod = candidate.product_integration
    if prod == ProductIntegration.HEAVY_BRANDED.value:
        breakdown["brand_penalty"] = -0.18
        score -= 0.18
    elif prod == ProductIntegration.PROMINENT.value:
        breakdown["brand_penalty"] = -0.08
        score -= 0.08

    score = max(0.0, min(1.0, score))
    return score, breakdown


def _sort_key(item: tuple[AnalyzedCandidate, float, dict[str, float]]) -> float:
    return item[1]


def prioritize_for_tiers(
    scored: list[tuple[AnalyzedCandidate, float, dict[str, float]]],
    tier_demand: dict[str, int],
    *,
    max_total: int | None = None,
) -> list[tuple[AnalyzedCandidate, float, dict[str, float]]]:
    """Select candidates respecting per-tier quotas, then backfill by global score."""
    if not scored:
        return []

    by_tier: dict[str, list[tuple[AnalyzedCandidate, float, dict[str, float]]]] = {}
    for row in scored:
        tier = row[0].raw.content_tier or "standard"
        by_tier.setdefault(tier, []).append(row)
    for bucket in by_tier.values():
        bucket.sort(key=_sort_key, reverse=True)

    picked: list[tuple[AnalyzedCandidate, float, dict[str, float]]] = []
    picked_ids: set[str] = set()

    if tier_demand:
        for tier, need in tier_demand.items():
            if need <= 0:
                continue
            bucket = by_tier.get(tier, [])
            for row in bucket[:need]:
                cid = row[0].raw.candidate_id
                if cid not in picked_ids:
                    picked.append(row)
                    picked_ids.add(cid)

    remaining_pool = sorted(scored, key=_sort_key, reverse=True)
    total_cap = max_total if max_total is not None else len(scored)
    for row in remaining_pool:
        if len(picked) >= total_cap:
            break
        cid = row[0].raw.candidate_id
        if cid not in picked_ids:
            picked.append(row)
            picked_ids.add(cid)

    return picked[:total_cap] if total_cap else picked
