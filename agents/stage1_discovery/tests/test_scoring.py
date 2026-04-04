from __future__ import annotations

from abunny_stage1_discovery.analysis_enums import HookLabel, ProductIntegration
from abunny_stage1_discovery.models import AnalyzedCandidate, RawShortCandidate, TranscriptSegment
from abunny_stage1_discovery.scoring import copyability_score, prioritize_for_tiers


def _raw(cid: str, tier: str) -> RawShortCandidate:
    return RawShortCandidate(candidate_id=cid, source_url="https://ex.test", platform="tiktok", content_tier=tier)


def test_copyability_prefers_transcript_and_strong_hook() -> None:
    weak = AnalyzedCandidate(raw=_raw("1", "standard"), transcript=[], hook_label=HookLabel.UNKNOWN.value)
    strong = AnalyzedCandidate(
        raw=_raw("2", "standard"),
        transcript=[TranscriptSegment(start_seconds=0, end_seconds=1, text="hi")],
        hook_label=HookLabel.PATTERN_INTERRUPT.value,
    )
    s_weak, _ = copyability_score(weak)
    s_strong, br = copyability_score(strong)
    assert s_strong > s_weak
    assert "transcript" in br or "hook_strength" in br


def test_heavy_branded_penalty() -> None:
    base = AnalyzedCandidate(
        raw=_raw("a", "standard"),
        transcript=[TranscriptSegment(start_seconds=0, end_seconds=1, text="x")],
        hook_label=HookLabel.TUTORIAL.value,
        product_integration=ProductIntegration.NONE.value,
    )
    branded = AnalyzedCandidate(
        raw=_raw("b", "standard"),
        transcript=base.transcript,
        hook_label=base.hook_label,
        product_integration=ProductIntegration.HEAVY_BRANDED.value,
    )
    s_base, _ = copyability_score(base)
    s_brand, br = copyability_score(branded)
    assert s_base > s_brand
    assert br.get("brand_penalty", 0) < 0


def test_prioritize_respects_tier_quotas() -> None:
    candidates = [
        AnalyzedCandidate(
            raw=_raw("v1", "viral"),
            transcript=[TranscriptSegment(start_seconds=0, end_seconds=1, text="a")],
            hook_label=HookLabel.UNKNOWN.value,
        ),
        AnalyzedCandidate(
            raw=_raw("v2", "viral"),
            transcript=[TranscriptSegment(start_seconds=0, end_seconds=1, text="b")],
            hook_label=HookLabel.PATTERN_INTERRUPT.value,
        ),
        AnalyzedCandidate(
            raw=_raw("s1", "standard"),
            transcript=[TranscriptSegment(start_seconds=0, end_seconds=1, text="c")],
            hook_label=HookLabel.UNKNOWN.value,
        ),
        AnalyzedCandidate(
            raw=_raw("s2", "standard"),
            transcript=[TranscriptSegment(start_seconds=0, end_seconds=1, text="d")],
            hook_label=HookLabel.UNKNOWN.value,
        ),
    ]
    scored = [(c, *copyability_score(c)) for c in candidates]
    picked = prioritize_for_tiers(scored, {"viral": 1, "standard": 1}, max_total=2)
    ids = {p[0].raw.candidate_id for p in picked}
    assert len(ids) == 2
    assert "v2" in ids or "v1" in ids
    assert "s1" in ids or "s2" in ids
