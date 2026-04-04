"""
Seed data factories for m2t4 end-to-end smoke tests and handoff validation.

All factories return deterministic objects with fixed IDs so test output is
reproducible. Override individual fields via kwargs.

The stage boundary adapters near the bottom handle the field-name mismatches
between stage contracts that haven't been unified yet.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Stage 0 / Stage 3 — IdentityMatrix, ContentPackage, DistributionRecord
# These live in stage3's local contracts right now.
# ---------------------------------------------------------------------------

from agents.stage3_distribution.contracts import (
    CommentStyle,
    ContentPackage as S3ContentPackage,
    DistributionRecord as S3DistributionRecord,
    DistributionStatus,
    IdentityMatrix,
    Platform as S3Platform,
)

# ---------------------------------------------------------------------------
# Stage 4 — DistributionRecord (different field names), PerformanceMetricRecord
# ---------------------------------------------------------------------------

from agents.stage4_analytics.contracts import (
    ContentPackage as S4ContentPackage,
    DistributionRecord as S4DistributionRecord,
    IdentityMatrix as S4IdentityMatrix,
    PerformanceMetricRecord,
    OptimizationDirectiveEnvelope,
    RedoQueueItem,
    VideoBlueprint,
)


# ---------------------------------------------------------------------------
# Fixed IDs for reproducible runs
# ---------------------------------------------------------------------------

IDENTITY_ID = "00000000-0000-0000-0000-000000000001"
BLUEPRINT_ID = "00000000-0000-0000-0000-000000000002"
PACKAGE_ID = "00000000-0000-0000-0000-000000000010"
DIST_RECORD_ID = "00000000-0000-0000-0000-000000000020"

_FIXTURE_DIR = Path(__file__).parents[2] / "examples" / "m2" / "stage3" / "fixtures"
_ANALYTICS_FIXTURE = Path(__file__).parents[2] / "tests" / "stage34" / "stage4" / "fixtures" / "sample_analytics.json"


# ---------------------------------------------------------------------------
# Stage 0 output
# ---------------------------------------------------------------------------


def make_identity(**overrides: Any) -> IdentityMatrix:
    """Canonical bunnygirl persona — Stage 0 output."""
    defaults: dict[str, Any] = dict(
        identity_id=IDENTITY_ID,
        persona_name="bunnygirl",
        display_name="Bunny 🐰",
        niche="fashion",
        bio="Your fave bunnygirl serving lewks daily 🐰✨ | AI-assisted content creator",
        visual_style="pastel aesthetic, oversized fits",
        voice_tags=["playful", "warm", "confident"],
        hashtags=["#bunnygirl", "#fashioninspo", "#ootd"],
        target_platforms=[S3Platform.TIKTOK, S3Platform.INSTAGRAM],
        comment_style=CommentStyle(
            tone="friendly",
            use_emojis=True,
            avg_reply_length=80,
            trigger_keywords=["link", "where", "buy", "how", "price", "shop"],
            dm_offer_template="Hey babe! DM me and I'll send you the link 🐰✨",
            positive_reply_templates=["Thank you so much this means everything 🥰"],
            question_reply_templates=["Great question! {answer} 🐰"],
            faq={"outfit": "Linked in bio or DM me!"},
        ),
        ai_disclosure_footer="✨ AI-assisted content | @{persona_name}",
    )
    defaults.update(overrides)
    return IdentityMatrix(**defaults)


def load_identity_from_fixture() -> IdentityMatrix:
    """Load the canonical identity fixture from examples/stage3/fixtures/."""
    data = json.loads((_FIXTURE_DIR / "identity_matrix.json").read_text(encoding="utf-8"))
    return IdentityMatrix.model_validate(data)


# ---------------------------------------------------------------------------
# Stage 1 output (VideoBlueprint lives in stage4 contracts for now)
# ---------------------------------------------------------------------------


def make_video_blueprint(**overrides: Any) -> VideoBlueprint:
    """Representative VideoBlueprint — Stage 1/2 boundary output."""
    defaults: dict[str, Any] = dict(
        blueprint_id=BLUEPRINT_ID,
        hook_style="question",
        duration_seconds=28,
        topic="5 pastel fits for spring",
        niche_tags=["fashion", "aesthetics", "ootd"],
    )
    defaults.update(overrides)
    return VideoBlueprint(**defaults)


# ---------------------------------------------------------------------------
# Stage 2 output (ContentPackage — stage3 variant consumed by Stage 3)
# ---------------------------------------------------------------------------


def make_content_package(**overrides: Any) -> S3ContentPackage:
    """ContentPackage as Stage 2 produces it — consumed by Stage 3."""
    defaults: dict[str, Any] = dict(
        package_id=PACKAGE_ID,
        blueprint_id=BLUEPRINT_ID,
        content_type="short_video",
        title="5 pastel fits for spring 🐰",
        caption="POV: your closet is giving main character energy ✨\n\nWhich look is your fave? 👇",
        hashtags=["#bunnygirl", "#springfashion", "#outfitcheck", "#aesthetic", "#ootd"],
        media_path=None,
        media_url=None,
        duration_seconds=28.5,
        target_platforms=[S3Platform.TIKTOK, S3Platform.INSTAGRAM],
        priority=2,
        identity_id=IDENTITY_ID,
    )
    defaults.update(overrides)
    return S3ContentPackage(**defaults)


def load_package_from_fixture() -> S3ContentPackage:
    """Load the canonical content package fixture from examples/stage3/fixtures/."""
    data = json.loads((_FIXTURE_DIR / "content_package.json").read_text(encoding="utf-8"))
    return S3ContentPackage.model_validate(data)


# ---------------------------------------------------------------------------
# Stage 3 output (DistributionRecord — the contract Stage 4 must accept)
# ---------------------------------------------------------------------------


def make_s3_distribution_record(**overrides: Any) -> S3DistributionRecord:
    """DistributionRecord as Stage 3 produces it."""
    defaults: dict[str, Any] = dict(
        record_id=DIST_RECORD_ID,
        package_id=PACKAGE_ID,
        identity_id=IDENTITY_ID,
        platform=S3Platform.TIKTOK,
        post_id="DRY-RUN-abc12345",
        post_url=None,
        status=DistributionStatus.DRY_RUN,
        caption_used="Test caption\n\n✨ AI-assisted content | @bunnygirl",
        hashtags_used=["#bunnygirl", "#test"],
        dry_run=True,
        provider_used="mock",
    )
    defaults.update(overrides)
    return S3DistributionRecord(**defaults)


# ---------------------------------------------------------------------------
# S3 → S4 boundary adapter
# Translates stage3's DistributionRecord field names to stage4's.
# This is the handoff seam — a future packages/contracts unification would
# eliminate it.
# ---------------------------------------------------------------------------

_STATUS_MAP: dict[str, str] = {
    "posted": "posted",
    "failed": "failed",
    "dry_run": "dry_run",
    "scheduled": "scheduled",
    "queued": "scheduled",    # stage4 has no "queued"; map to scheduled
    "executing": "scheduled",  # idem
    "skipped": "failed",      # closest equivalent
}


def adapt_s3_to_s4_distribution_record(
    s3_record: S3DistributionRecord,
    video_blueprint_id: str | None = None,
    audio_id: str | None = None,
    schedule_slot: str | None = None,
) -> S4DistributionRecord:
    """
    Convert a Stage 3 DistributionRecord to the Stage 4 schema.

    Field mapping:
      s3.package_id         → s4.content_package_id
      s3.platform (enum)    → s4.platform (str)
      s3.status (enum)      → s4.status (Literal)
      s3.posted_at          → s4.posted_at
      s3.dry_run            → s4.dry_run
    """
    s4_status = _STATUS_MAP.get(s3_record.status.value, "failed")
    return S4DistributionRecord(
        record_id=s3_record.record_id,
        content_package_id=s3_record.package_id,
        video_blueprint_id=video_blueprint_id,
        platform=s3_record.platform.value,
        post_id=s3_record.post_id,
        post_url=s3_record.post_url,
        posted_at=s3_record.posted_at,
        status=s4_status,
        audio_id=audio_id,
        schedule_slot=schedule_slot,
        dry_run=s3_record.dry_run,
    )


# ---------------------------------------------------------------------------
# Stage 4 fixtures from the canonical analytics fixture file
# ---------------------------------------------------------------------------


def load_s4_distribution_records() -> list[S4DistributionRecord]:
    """Load the 10-post fixture dataset as Stage 4 DistributionRecords."""
    raw = json.loads(_ANALYTICS_FIXTURE.read_text(encoding="utf-8"))
    return [
        S4DistributionRecord(
            record_id=f"dist_{i:03d}",
            content_package_id=f"pkg_{i:03d}",
            video_blueprint_id=f"bp_{i:03d}",
            platform=post["platform"],
            post_id=post["post_id"],
            status="posted",
            audio_id=post.get("audio_id"),
            schedule_slot=post.get("schedule_slot"),
        )
        for i, post in enumerate(raw["posts"])
    ]
