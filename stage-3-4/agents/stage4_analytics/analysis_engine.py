"""
Stage 4 analysis engine.

Runs 5 dimensional analyses over a list of PerformanceMetricRecords:
  1. hook        — which hook_styles retain viewers vs. lose them
  2. content_tier — hero/hub/hygiene ROI relative to effort signal
  3. schedule    — which time slots outperform baseline
  4. product     — which product_ids drive revenue
  5. audio_trend — which audio_ids correlate with higher engagement

Each dimension produces an AnalysisResult with scored slices and a flag
indicating whether a directive is warranted.

Thresholds are configurable via AnalyticsConfig (all defaults are set for
a mid-size creator: 10k–100k followers, TikTok/Instagram mix).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean

from .contracts import PerformanceMetricRecord
from .models import AnalysisBundle, AnalysisDimension, AnalysisResult, DimensionScore

# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------


@dataclass
class AnalyticsConfig:
    """
    All scoring thresholds in one place.

    label ranges (engagement_rate_pct):
        excellent  ≥ excellent_threshold
        good       ≥ good_threshold
        average    ≥ average_threshold
        poor       ≥ poor_threshold
        critical   < poor_threshold
    """
    # Engagement rate (%) thresholds
    excellent_threshold: float = 8.0
    good_threshold: float = 5.0
    average_threshold: float = 3.0
    poor_threshold: float = 1.5

    # Hook 3s retention (%) thresholds
    hook_excellent: float = 75.0
    hook_good: float = 60.0
    hook_poor: float = 40.0

    # Completion rate (%) thresholds
    completion_good: float = 40.0
    completion_poor: float = 20.0

    # Minimum posts needed for a dimension slice to be considered reliable
    min_sample_size: int = 2

    # A slice is a "bottom performer" if it's this many pp below the best slice
    bottom_performer_gap_pp: float = 2.0

    # Revenue threshold for product_focus directive (USD per post)
    product_focus_min_revenue: float = 5.0


DEFAULT_CONFIG = AnalyticsConfig()


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _label(value: float, config: AnalyticsConfig) -> str:
    if value >= config.excellent_threshold:
        return "excellent"
    if value >= config.good_threshold:
        return "good"
    if value >= config.average_threshold:
        return "average"
    if value >= config.poor_threshold:
        return "poor"
    return "critical"


def _group_by(
    records: list[PerformanceMetricRecord],
    key: str,
) -> dict[str, list[PerformanceMetricRecord]]:
    groups: dict[str, list[PerformanceMetricRecord]] = defaultdict(list)
    for r in records:
        k = getattr(r, key, None)
        if k:
            groups[k].append(r)
    return dict(groups)


def _score_group(
    dimension: AnalysisDimension,
    slice_key: str,
    records: list[PerformanceMetricRecord],
    config: AnalyticsConfig,
) -> DimensionScore:
    eng = mean(r.engagement_rate_pct for r in records)
    comp = mean(r.completion_rate_pct for r in records)
    hook = mean(r.hook_retention_3s_pct for r in records)
    views = mean(r.views for r in records)
    rev = mean(r.revenue_attributed for r in records)
    return DimensionScore(
        dimension=dimension,
        slice_key=slice_key,
        avg_engagement_rate=round(eng, 2),
        avg_completion_rate=round(comp, 2),
        avg_hook_retention_3s=round(hook, 2),
        avg_views=round(views, 1),
        avg_revenue=round(rev, 2),
        sample_size=len(records),
        performance_label=_label(eng, config),
    )


def _top_bottom(
    scores: list[DimensionScore], config: AnalyticsConfig
) -> tuple[list[str], list[str]]:
    if not scores:
        return [], []
    best = scores[0].avg_engagement_rate
    tops = [s.slice_key for s in scores if s.performance_label in ("excellent", "good")]
    bots = [
        s.slice_key for s in scores
        if (best - s.avg_engagement_rate) >= config.bottom_performer_gap_pp
        or s.performance_label in ("poor", "critical")
    ]
    return tops, bots


# ---------------------------------------------------------------------------
# Dimension analysers
# ---------------------------------------------------------------------------


def _analyse_hook(
    records: list[PerformanceMetricRecord],
    config: AnalyticsConfig,
) -> AnalysisResult:
    groups = _group_by(records, "hook_style")
    scores = sorted(
        [
            _score_group(AnalysisDimension.HOOK, k, v, config)
            for k, v in groups.items()
            if len(v) >= config.min_sample_size
        ],
        key=lambda s: s.avg_engagement_rate,
        reverse=True,
    )
    tops, bots = _top_bottom(scores, config)
    # Hook-specific: also flag low 3s retention as "hook_failed"
    poor_hook_3s = [
        s.slice_key for s in scores if s.avg_hook_retention_3s < config.hook_poor
    ]
    if poor_hook_3s:
        bots = list(set(bots + poor_hook_3s))
    directive = bool(bots) and bool(tops)  # only issue directive if there's a clear winner
    notes = f"Analysed {len(scores)} hook styles. Poor 3s retention: {poor_hook_3s}."
    return AnalysisResult(
        dimension=AnalysisDimension.HOOK,
        scores=scores,
        top_performers=tops,
        bottom_performers=bots,
        directive_warranted=directive,
        analysis_notes=notes,
    )


def _analyse_content_tier(
    records: list[PerformanceMetricRecord],
    config: AnalyticsConfig,
) -> AnalysisResult:
    groups = _group_by(records, "content_tier")
    scores = sorted(
        [
            _score_group(AnalysisDimension.CONTENT_TIER, k, v, config)
            for k, v in groups.items()
            if len(v) >= config.min_sample_size
        ],
        key=lambda s: s.avg_engagement_rate,
        reverse=True,
    )
    tops, bots = _top_bottom(scores, config)
    counts = {k: len(v) for k, v in groups.items()}
    directive = bool(bots)
    notes = (
        f"Tier distribution: {counts}. "
        f"Best: {scores[0].slice_key if scores else 'n/a'}."
    )
    for s in scores:
        s.metadata["post_count"] = counts.get(s.slice_key, 0)
    return AnalysisResult(
        dimension=AnalysisDimension.CONTENT_TIER,
        scores=scores,
        top_performers=tops,
        bottom_performers=bots,
        directive_warranted=directive,
        analysis_notes=notes,
    )


def _analyse_schedule(
    records: list[PerformanceMetricRecord],
    config: AnalyticsConfig,
) -> AnalysisResult:
    groups = _group_by(records, "schedule_slot")
    scores = sorted(
        [
            _score_group(AnalysisDimension.SCHEDULE, k, v, config)
            for k, v in groups.items()
            if len(v) >= config.min_sample_size
        ],
        key=lambda s: s.avg_engagement_rate,
        reverse=True,
    )
    tops, bots = _top_bottom(scores, config)
    directive = bool(bots) and len(scores) >= 2
    notes = (
        f"Analysed {len(scores)} schedule slots. "
        f"Best slot: {scores[0].slice_key if scores else 'n/a'}, "
        f"worst: {scores[-1].slice_key if scores else 'n/a'}."
    )
    return AnalysisResult(
        dimension=AnalysisDimension.SCHEDULE,
        scores=scores,
        top_performers=tops,
        bottom_performers=bots,
        directive_warranted=directive,
        analysis_notes=notes,
    )


def _analyse_product(
    records: list[PerformanceMetricRecord],
    config: AnalyticsConfig,
) -> AnalysisResult:
    groups = _group_by(records, "product_id")
    scores = sorted(
        [
            _score_group(AnalysisDimension.PRODUCT, k, v, config)
            for k, v in groups.items()
            if len(v) >= config.min_sample_size
        ],
        key=lambda s: s.avg_revenue,
        reverse=True,
    )
    # For products, sort by revenue not engagement
    tops = [s.slice_key for s in scores if s.avg_revenue >= config.product_focus_min_revenue]
    bots = [s.slice_key for s in scores if s.avg_revenue < config.product_focus_min_revenue]
    directive = bool(tops) and bool(bots)
    top_rev = scores[0].slice_key if scores else "n/a"
    notes = f"Analysed {len(scores)} products. Top revenue: {top_rev}."
    return AnalysisResult(
        dimension=AnalysisDimension.PRODUCT,
        scores=scores,
        top_performers=tops,
        bottom_performers=bots,
        directive_warranted=directive,
        analysis_notes=notes,
    )


def _analyse_audio_trend(
    records: list[PerformanceMetricRecord],
    config: AnalyticsConfig,
) -> AnalysisResult:
    groups = _group_by(records, "audio_id")
    scores = sorted(
        [
            _score_group(AnalysisDimension.AUDIO_TREND, k, v, config)
            for k, v in groups.items()
            if len(v) >= config.min_sample_size
        ],
        key=lambda s: s.avg_engagement_rate,
        reverse=True,
    )
    tops, bots = _top_bottom(scores, config)
    directive = bool(bots) and bool(tops)
    notes = (
        f"Analysed {len(scores)} audio tracks. "
        f"Top: {scores[0].slice_key if scores else 'n/a'}, "
        f"bottom: {bots}."
    )
    return AnalysisResult(
        dimension=AnalysisDimension.AUDIO_TREND,
        scores=scores,
        top_performers=tops,
        bottom_performers=bots,
        directive_warranted=directive,
        analysis_notes=notes,
    )


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class AnalysisEngine:
    """
    Runs all 5 dimensional analyses and returns an AnalysisBundle.

    Usage:
        engine = AnalysisEngine()
        bundle = engine.analyse(records, window_days=7)
    """

    def __init__(self, config: AnalyticsConfig | None = None) -> None:
        self._config = config or DEFAULT_CONFIG

    def analyse(
        self,
        records: list[PerformanceMetricRecord],
        window_days: int = 7,
    ) -> AnalysisBundle:
        if not records:
            return AnalysisBundle(window_days=window_days, record_count=0)

        global_eng = mean(r.engagement_rate_pct for r in records)
        global_comp = mean(r.completion_rate_pct for r in records)

        return AnalysisBundle(
            window_days=window_days,
            record_count=len(records),
            hook=_analyse_hook(records, self._config),
            content_tier=_analyse_content_tier(records, self._config),
            schedule=_analyse_schedule(records, self._config),
            product=_analyse_product(records, self._config),
            audio_trend=_analyse_audio_trend(records, self._config),
            global_avg_engagement=round(global_eng, 2),
            global_avg_completion=round(global_comp, 2),
        )
