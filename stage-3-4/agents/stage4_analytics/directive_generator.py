"""
Directive generator for Stage 4.

Maps AnalysisBundle results to typed OptimizationDirectiveEnvelope objects.
Each dimension that has `directive_warranted=True` produces one or more
directives targeted at the appropriate upstream stage.

Target stage mapping:
    hook          → stage2 (change how blueprints are written)
    content_tier  → stage2 (rebalance tier ratios)
    schedule      → stage3 (change when posts go out)
    product       → stage2 + stage3 (change featured products + posting focus)
    audio_trend   → stage1 + stage2 (discover better audio + use it in blueprints)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .contracts import OptimizationDirectiveEnvelope
from .models import AnalysisBundle, AnalysisDimension, AnalysisResult


def _expires(days: int = 7) -> datetime:
    return datetime.utcnow() + timedelta(days=days)


def _hook_directives(result: AnalysisResult, dry_run: bool) -> list[OptimizationDirectiveEnvelope]:
    if not result.directive_warranted:
        return []
    best = result.scores[0] if result.scores else None
    worst_styles = result.bottom_performers
    example_hooks: list[str] = []
    if best:
        example_hooks = [
            f"Use {best.slice_key}-style hooks (avg {best.avg_engagement_rate:.1f}% eng rate)"
        ]
    priority = "critical" if any(
        s.performance_label == "critical" for s in result.scores if s.slice_key in worst_styles
    ) else "high"
    return [
        OptimizationDirectiveEnvelope(
            analysis_window_days=7,
            target_stage="stage2",
            directive_type="hook_rewrite",
            priority=priority,
            rationale=(
                f"Hook styles {worst_styles} are underperforming. "
                f"Best style: {best.slice_key if best else 'unknown'} "
                f"({best.avg_engagement_rate:.1f}% eng, "
                f"{best.avg_hook_retention_3s:.1f}% 3s retention). "
                f"{result.analysis_notes}"
            ),
            payload={
                "hook_style": best.slice_key if best else None,
                "example_hooks": example_hooks,
                "avoid_styles": worst_styles,
                "target_3s_retention_pct": 60.0,
            },
            expires_at=_expires(7),
            dry_run=dry_run,
        )
    ]


def _schedule_directives(
    result: AnalysisResult, dry_run: bool
) -> list[OptimizationDirectiveEnvelope]:
    if not result.directive_warranted or not result.scores:
        return []
    best = result.scores[0]
    directives = []
    for bad_slot in result.bottom_performers:
        bad_score = next((s for s in result.scores if s.slice_key == bad_slot), None)
        bad_eng = bad_score.avg_engagement_rate if bad_score else 0
        lift = round(best.avg_engagement_rate - bad_eng, 1)
        directives.append(
            OptimizationDirectiveEnvelope(
                analysis_window_days=7,
                target_stage="stage3",
                directive_type="schedule_shift",
                priority="high" if lift > 3.0 else "medium",
                rationale=(
                    f"Slot '{bad_slot}' averaged {bad_score.avg_engagement_rate:.1f}% eng vs "
                    f"'{best.slice_key}' at {best.avg_engagement_rate:.1f}% - "
                    f"{lift:.1f} pp lift available. {result.analysis_notes}"
                ),
                payload={
                    "current_slot": bad_slot,
                    "recommended_slot": best.slice_key,
                    "lift_pct": lift,
                },
                expires_at=_expires(14),
                dry_run=dry_run,
            )
        )
    return directives


def _content_tier_directives(
    result: AnalysisResult, dry_run: bool
) -> list[OptimizationDirectiveEnvelope]:
    if not result.directive_warranted or not result.scores:
        return []
    current_ratio = {
        s.slice_key: s.metadata.get("post_count", s.sample_size) for s in result.scores
    }
    total = sum(current_ratio.values()) or 1
    current_pct = {k: round(v / total * 100) for k, v in current_ratio.items()}
    # Target: shift weight toward top performers, reduce bottom performers
    top_keys = result.top_performers or [result.scores[0].slice_key]
    target_pct: dict[str, int] = {}
    n = len(result.scores)
    for s in result.scores:
        if s.slice_key in top_keys:
            target_pct[s.slice_key] = 100 // max(1, len(top_keys)) if n <= 2 else 50
        else:
            target_pct[s.slice_key] = max(10, current_pct.get(s.slice_key, 33) - 10)
    return [
        OptimizationDirectiveEnvelope(
            analysis_window_days=7,
            target_stage="stage2",
            directive_type="content_tier_rebalance",
            priority="medium",
            rationale=(
                f"Content tier performance gap detected. "
                f"Top: {result.top_performers}, bottom: {result.bottom_performers}. "
                f"{result.analysis_notes}"
            ),
            payload={
                "current_ratio": current_pct,
                "target_ratio": target_pct,
            },
            expires_at=_expires(14),
            dry_run=dry_run,
        )
    ]


def _audio_directives(result: AnalysisResult, dry_run: bool) -> list[OptimizationDirectiveEnvelope]:
    if not result.directive_warranted or not result.scores:
        return []
    return [
        OptimizationDirectiveEnvelope(
            analysis_window_days=7,
            target_stage="stage1+stage2",
            directive_type="audio_swap",
            priority="medium",
            rationale=(
                f"Audio tracks {result.bottom_performers} correlate with below-average engagement. "
                f"Top audio: {result.top_performers}. {result.analysis_notes}"
            ),
            payload={
                "avoid_audio_ids": result.bottom_performers,
                "preferred_audio_ids": result.top_performers,
            },
            expires_at=_expires(7),
            dry_run=dry_run,
        )
    ]


def _product_directives(
    result: AnalysisResult, dry_run: bool
) -> list[OptimizationDirectiveEnvelope]:
    if not result.directive_warranted or not result.scores:
        return []
    return [
        OptimizationDirectiveEnvelope(
            analysis_window_days=7,
            target_stage="stage2",
            directive_type="product_focus",
            priority="high" if result.scores[0].avg_revenue > 20.0 else "medium",
            rationale=(
                f"Revenue concentration: {result.top_performers} drive most attributed revenue. "
                f"Low performers: {result.bottom_performers}. {result.analysis_notes}"
            ),
            payload={
                "top_product_ids": result.top_performers,
                "drop_product_ids": result.bottom_performers,
            },
            expires_at=_expires(14),
            dry_run=dry_run,
        )
    ]


_DIMENSION_HANDLERS = {
    AnalysisDimension.HOOK: _hook_directives,
    AnalysisDimension.SCHEDULE: _schedule_directives,
    AnalysisDimension.CONTENT_TIER: _content_tier_directives,
    AnalysisDimension.AUDIO_TREND: _audio_directives,
    AnalysisDimension.PRODUCT: _product_directives,
}


class DirectiveGenerator:
    """
    Converts an AnalysisBundle into a list of OptimizationDirectiveEnvelopes.

    Directives are deterministic: same bundle → same directives (modulo UUIDs
    and timestamps). Tests should compare payload contents, not envelope_id.
    """

    def generate(
        self,
        bundle: AnalysisBundle,
        dry_run: bool = False,
    ) -> list[OptimizationDirectiveEnvelope]:
        directives: list[OptimizationDirectiveEnvelope] = []
        dimension_results = {
            AnalysisDimension.HOOK: bundle.hook,
            AnalysisDimension.CONTENT_TIER: bundle.content_tier,
            AnalysisDimension.SCHEDULE: bundle.schedule,
            AnalysisDimension.PRODUCT: bundle.product,
            AnalysisDimension.AUDIO_TREND: bundle.audio_trend,
        }
        for dim, result in dimension_results.items():
            if result is None:
                continue
            handler = _DIMENSION_HANDLERS[dim]
            directives.extend(handler(result, dry_run))
        # Sort by priority so consumers process the most critical first
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        directives.sort(key=lambda d: priority_order.get(d.priority, 99))
        return directives
