from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipeline_contracts.models import VideoBlueprint

from abunny_stage1_discovery.analysis_enums import CtaKind, HookLabel, ProductIntegration


class ContentTierDemand(BaseModel):
    """Per-tier counts Stage 1 should try to fill (advisory for planner and queue)."""

    model_config = ConfigDict(extra="forbid")

    tiers: dict[str, int] = Field(
        default_factory=dict,
        description="Logical tier name → desired blueprint count (non-negative ints).",
    )

    @field_validator("tiers")
    @classmethod
    def _non_negative(cls, v: dict[str, int]) -> dict[str, int]:
        for k, n in v.items():
            if n < 0:
                msg = f"tier {k!r} demand must be >= 0"
                raise ValueError(msg)
        return v


class DiscoveryPlan(BaseModel):
    """Planned discovery scope derived from identity, directives, and tier demand."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    matrix_id: str
    niche: str
    platforms: list[str] = Field(default_factory=list)
    seed_queries: list[str] = Field(default_factory=list)
    seed_handles: list[str] = Field(default_factory=list)
    max_candidates: int = Field(default=20, ge=1, le=500)
    tier_targets: dict[str, int] = Field(default_factory=dict)
    directive_notes: list[str] = Field(default_factory=list)


class RawShortCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    source_url: str
    platform: str
    title: str | None = None
    creator_handle: str | None = None
    thumbnail_url: str | None = None
    content_tier: str = Field(default="standard", description="Planner/queue tier label.")


class AccountMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handle: str
    platform: str
    display_name: str | None = None
    follower_count_approx: int | None = Field(default=None, ge=0)
    bio: str | None = None


class MediaDownloadJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    candidate_id: str
    source_url: str
    priority: int = Field(default=0, description="Higher runs first.")
    asset_kind: str = Field(default="video", description="video | audio | thumb")


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    text: str


class OverlayCutPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t_seconds: float = Field(ge=0.0)
    kind: str = Field(description="overlay | jump_cut | beat")


class AnalyzedCandidate(BaseModel):
    """Enriched candidate after analysis adapters (pre-blueprint, pre-score)."""

    model_config = ConfigDict(extra="forbid")

    raw: RawShortCandidate
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    hook_label: str = Field(default=HookLabel.UNKNOWN.value)
    overlay_cut_points: list[OverlayCutPoint] = Field(default_factory=list)
    cta_kind: str = Field(default=CtaKind.NONE.value)
    product_integration: str = Field(default=ProductIntegration.NONE.value)


class RankedQueueItem(BaseModel):
    """Prioritized blueprint slot with copyability metadata for Stage 2."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    blueprint_id: str
    copyability_score: float = Field(ge=0.0, le=1.0)
    content_tier: str
    candidate_id: str
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class Stage1Artifacts(BaseModel):
    """Serialized handoff bundle (JSON-friendly)."""

    model_config = ConfigDict(extra="forbid")

    video_blueprints: list[dict] = Field(default_factory=list)
    trending_audio: list[dict] = Field(default_factory=list)
    competitor_watchlist: list[dict] = Field(default_factory=list)
    ranked_queue: list[dict] = Field(default_factory=list)
    discovery_plan: dict | None = None


class Stage1RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blueprints: list[VideoBlueprint]
    trending_audio: list
    competitor_watchlist: list
    ranked_queue: list[RankedQueueItem]
    plan: DiscoveryPlan

    def to_artifacts(self) -> Stage1Artifacts:
        return Stage1Artifacts(
            video_blueprints=[b.model_dump(mode="json") for b in self.blueprints],
            trending_audio=[x if isinstance(x, dict) else x.model_dump(mode="json") for x in self.trending_audio],
            competitor_watchlist=[
                x if isinstance(x, dict) else x.model_dump(mode="json") for x in self.competitor_watchlist
            ],
            ranked_queue=[q.model_dump(mode="json") for q in self.ranked_queue],
            discovery_plan=self.plan.model_dump(mode="json"),
        )
