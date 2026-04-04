"""
Baseline tracker and summary writer for Stage 4.

BaselineUpdater:
  Maintains a rolling baseline of avg engagement/completion/views per
  platform+niche. Stored in the state adapter and consulted by the
  analysis engine when labelling performance.

SummaryWriter:
  Produces human-readable daily/weekly Markdown summaries from an
  AnalysisBundle + list of directives + redo queue items.
"""
from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import TYPE_CHECKING

from .contracts import OptimizationDirectiveEnvelope, PerformanceMetricRecord, RedoQueueItem
from .models import AnalysisBundle, BaselineSnapshot

if TYPE_CHECKING:
    from .state_adapter import StateAdapter


class BaselineUpdater:
    """
    Computes and persists rolling baselines per (platform, niche).

    Usage:
        updater = BaselineUpdater(adapter)
        updater.update(records, niche="beauty")
        snapshot = updater.get("tiktok", "beauty")
    """

    def __init__(self, adapter: StateAdapter) -> None:
        self._adapter = adapter

    def update(
        self,
        records: list[PerformanceMetricRecord],
        niche: str = "general",
    ) -> list[BaselineSnapshot]:
        """
        Recompute baselines from the provided records (per platform).
        Persists updated snapshots and returns them.
        """
        by_platform: dict[str, list[PerformanceMetricRecord]] = {}
        for r in records:
            by_platform.setdefault(r.platform, []).append(r)

        snapshots: list[BaselineSnapshot] = []
        for platform, platform_records in by_platform.items():
            if not platform_records:
                continue
            snapshot = BaselineSnapshot(
                platform=platform,
                niche=niche,
                avg_engagement_rate=round(mean(r.engagement_rate_pct for r in platform_records), 2),
                avg_completion_rate=round(mean(r.completion_rate_pct for r in platform_records), 2),
                avg_views=round(mean(r.views for r in platform_records), 1),
                avg_hook_retention_3s=round(
                    mean(r.hook_retention_3s_pct for r in platform_records), 2
                ),
                avg_revenue_per_post=round(mean(r.revenue_attributed for r in platform_records), 2),
                sample_size=len(platform_records),
                updated_at=datetime.utcnow().isoformat(),
            )
            self._adapter.save_baseline(snapshot)
            snapshots.append(snapshot)
        return snapshots

    def get(self, platform: str, niche: str = "general") -> BaselineSnapshot | None:
        return self._adapter.load_baseline(platform, niche)


class SummaryWriter:
    """Generates Markdown summary reports from Stage 4 analysis outputs."""

    def daily(
        self,
        bundle: AnalysisBundle,
        directives: list[OptimizationDirectiveEnvelope],
        redo_items: list[RedoQueueItem],
        date: datetime | None = None,
    ) -> str:
        date = date or datetime.utcnow()
        lines = [
            f"# Stage 4 Daily Summary - {date.strftime('%Y-%m-%d')}",
            "",
            f"**Records analysed:** {bundle.record_count}  ",
            f"**Global avg engagement:** {bundle.global_avg_engagement:.1f}%  ",
            f"**Global avg completion:** {bundle.global_avg_completion:.1f}%  ",
            "",
            "## Dimension Highlights",
        ]

        for dim_name, result in [
            ("Hook Performance", bundle.hook),
            ("Content Tier", bundle.content_tier),
            ("Schedule", bundle.schedule),
            ("Product", bundle.product),
            ("Audio/Trend", bundle.audio_trend),
        ]:
            if result is None:
                continue
            lines.append(f"\n### {dim_name}")
            lines.append(result.analysis_notes)
            if result.top_performers:
                lines.append(f"- **Top:** {', '.join(result.top_performers)}")
            if result.bottom_performers:
                lines.append(f"- **Needs work:** {', '.join(result.bottom_performers)}")

        lines += ["", f"## Directives Issued ({len(directives)})"]
        if directives:
            for d in directives:
                snippet = d.rationale[:100]
                lines.append(
                    f"- [{d.priority.upper()}] `{d.directive_type}`"
                    f" -> {d.target_stage}: {snippet}"
                )
        else:
            lines.append("_No directives issued._")

        lines += ["", f"## Redo Queue ({len(redo_items)} items)"]
        if redo_items:
            for item in redo_items:
                lines.append(
                    f"- [{item.priority.upper()}] `{item.redo_reason}` -> {item.target_stage} "
                    f"(dist: `{item.source_distribution_record_id[:8]}`)"
                )
        else:
            lines.append("_No redo items queued._")

        lines += ["", f"_Generated at {date.isoformat()}Z by Stage 4 / m2t3_"]
        return "\n".join(lines)

    def weekly(
        self,
        bundles: list[AnalysisBundle],
        directives: list[OptimizationDirectiveEnvelope],
        redo_items: list[RedoQueueItem],
        week_start: datetime | None = None,
    ) -> str:
        week_start = week_start or datetime.utcnow()
        total_records = sum(b.record_count for b in bundles)
        avg_eng = mean(b.global_avg_engagement for b in bundles) if bundles else 0.0
        avg_comp = mean(b.global_avg_completion for b in bundles) if bundles else 0.0

        lines = [
            f"# Stage 4 Weekly Summary - Week of {week_start.strftime('%Y-%m-%d')}",
            "",
            f"**Days analysed:** {len(bundles)}  ",
            f"**Total records:** {total_records}  ",
            f"**Avg engagement (7d):** {avg_eng:.1f}%  ",
            f"**Avg completion (7d):** {avg_comp:.1f}%  ",
            "",
            f"## Directives ({len(directives)} total)",
        ]
        by_type: dict[str, int] = {}
        for d in directives:
            by_type[d.directive_type] = by_type.get(d.directive_type, 0) + 1
        for dtype, count in sorted(by_type.items()):
            lines.append(f"- `{dtype}`: {count}")

        lines += [
            "",
            f"## Redo Queue ({len(redo_items)} total)",
            f"- Critical: {sum(1 for i in redo_items if i.priority == 'critical')}",
            f"- High: {sum(1 for i in redo_items if i.priority == 'high')}",
            f"- Medium: {sum(1 for i in redo_items if i.priority == 'medium')}",
            "",
            f"_Generated at {datetime.utcnow().isoformat()}Z by Stage 4 / m2t3_",
        ]
        return "\n".join(lines)
