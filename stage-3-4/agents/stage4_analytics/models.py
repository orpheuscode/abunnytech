"""
Internal analytics models for Stage 4.

These are not part of the public contract surface — they're intermediate
representations used within the analysis engine. Only contracts.py types
cross stage boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AnalysisDimension(StrEnum):
    HOOK = "hook"
    CONTENT_TIER = "content_tier"
    SCHEDULE = "schedule"
    PRODUCT = "product"
    AUDIO_TREND = "audio_trend"


@dataclass
class DimensionScore:
    """
    Scored result for a single slice of a dimension.

    e.g. hook_style="question" with avg_engagement_rate=4.2, sample_size=8
    """
    dimension: AnalysisDimension
    slice_key: str         # e.g. "question", "tue_18:00", "audio_abc123"
    avg_engagement_rate: float = 0.0
    avg_completion_rate: float = 0.0
    avg_hook_retention_3s: float = 0.0
    avg_views: float = 0.0
    avg_revenue: float = 0.0
    sample_size: int = 0
    performance_label: str = "average"  # "excellent" | "good" | "average" | "poor" | "critical"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """
    Aggregated analysis result for one dimension.

    Contains the ranked slices + the top and bottom performers.
    """
    dimension: AnalysisDimension
    scores: list[DimensionScore]       # sorted best → worst
    baseline_engagement_rate: float = 0.0
    baseline_completion_rate: float = 0.0
    top_performers: list[str] = field(default_factory=list)    # slice_key list
    bottom_performers: list[str] = field(default_factory=list)  # slice_key list
    directive_warranted: bool = False
    analysis_notes: str = ""


@dataclass
class AnalysisBundle:
    """
    Complete output of one analysis pass covering all 5 dimensions.
    Passed into the directive generator and redo queue generator.
    """
    window_days: int
    record_count: int
    hook: AnalysisResult | None = None
    content_tier: AnalysisResult | None = None
    schedule: AnalysisResult | None = None
    product: AnalysisResult | None = None
    audio_trend: AnalysisResult | None = None
    global_avg_engagement: float = 0.0
    global_avg_completion: float = 0.0


@dataclass
class BaselineSnapshot:
    """Persisted baseline for a platform+niche pair."""
    platform: str
    niche: str
    avg_engagement_rate: float
    avg_completion_rate: float
    avg_views: float
    avg_hook_retention_3s: float
    avg_revenue_per_post: float
    sample_size: int
    updated_at: str  # ISO datetime string
