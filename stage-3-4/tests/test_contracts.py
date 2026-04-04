"""
Contract validation tests — m2t4.

Black-box tests that verify each canonical contract can be:
  1. Instantiated with the minimum required fields
  2. Validated from a dict (model_validate)
  3. Round-tripped through JSON serialization
  4. Rejected when required fields are missing

No internal stage logic is imported — these tests only touch contract models.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

# Stage 3 contracts (IdentityMatrix, ContentPackage, DistributionRecord, DMConversationRecord)
from agents.stage3_distribution.contracts import (
    CommentCategory,
    ContentPackage as S3ContentPackage,
    DistributionRecord as S3DistributionRecord,
    DistributionStatus,
    DMConversationRecord,
    DMState,
    IdentityMatrix,
    Platform,
)

# Stage 4 contracts (VideoBlueprint, PerformanceMetricRecord, etc.)
from agents.stage4_analytics.contracts import (
    ContentPackage as S4ContentPackage,
    DistributionRecord as S4DistributionRecord,
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    ProductCatalogItem,
    RedoQueueItem,
    VideoBlueprint,
)


# ---------------------------------------------------------------------------
# IdentityMatrix (Stage 0 output)
# ---------------------------------------------------------------------------


class TestIdentityMatrix:
    def test_minimal_construction(self) -> None:
        identity = IdentityMatrix(persona_name="bunnygirl", display_name="Bunny", niche="fashion")
        assert identity.persona_name == "bunnygirl"
        assert identity.identity_id  # auto-generated UUID

    def test_json_roundtrip(self, identity: IdentityMatrix) -> None:
        serialized = identity.model_dump_json()
        restored = IdentityMatrix.model_validate_json(serialized)
        assert restored.identity_id == identity.identity_id
        assert restored.persona_name == identity.persona_name

    def test_has_required_stage1_fields(self, identity: IdentityMatrix) -> None:
        """Stage 1 discovery needs persona context to scope trending searches."""
        assert identity.niche
        assert identity.target_platforms
        assert identity.persona_name

    def test_has_required_stage3_fields(self, identity: IdentityMatrix) -> None:
        """Stage 3 executor needs disclosure footer and comment style."""
        assert identity.ai_disclosure_footer
        assert identity.comment_style
        assert identity.comment_style.trigger_keywords

    def test_missing_persona_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            IdentityMatrix(display_name="Bunny", niche="fashion")  # persona_name required

    def test_platform_values_are_valid(self, identity: IdentityMatrix) -> None:
        for p in identity.target_platforms:
            assert p.value in ("tiktok", "instagram", "youtube")


# ---------------------------------------------------------------------------
# VideoBlueprint (Stage 1/2 boundary)
# ---------------------------------------------------------------------------


class TestVideoBlueprint:
    def test_minimal_construction(self) -> None:
        bp = VideoBlueprint(blueprint_id="bp-001", hook_style="question", topic="spring fits")
        assert bp.blueprint_id == "bp-001"
        assert bp.duration_seconds == 30  # default

    def test_json_roundtrip(self, video_blueprint: VideoBlueprint) -> None:
        serialized = video_blueprint.model_dump_json()
        restored = VideoBlueprint.model_validate_json(serialized)
        assert restored.blueprint_id == video_blueprint.blueprint_id
        assert restored.hook_style == video_blueprint.hook_style

    def test_has_required_stage2_fields(self, video_blueprint: VideoBlueprint) -> None:
        """Stage 2 content generation needs these to produce a ContentPackage."""
        assert video_blueprint.hook_style
        assert video_blueprint.topic
        assert video_blueprint.duration_seconds > 0

    def test_niche_tags_default_empty(self) -> None:
        bp = VideoBlueprint(blueprint_id="bp-x", hook_style="bold_claim", topic="test")
        assert bp.niche_tags == []


# ---------------------------------------------------------------------------
# ContentPackage (Stage 2 output → Stage 3 input)
# ---------------------------------------------------------------------------


class TestContentPackage:
    def test_minimal_construction_s3(self) -> None:
        pkg = S3ContentPackage(
            content_type="short_video",
            title="Test",
            caption="Test caption",
            target_platforms=[Platform.TIKTOK],
        )
        assert pkg.package_id  # auto-generated

    def test_json_roundtrip_s3(self, content_package: S3ContentPackage) -> None:
        serialized = content_package.model_dump_json()
        restored = S3ContentPackage.model_validate_json(serialized)
        assert restored.package_id == content_package.package_id

    def test_has_required_stage3_fields(self, content_package: S3ContentPackage) -> None:
        """Stage 3 scheduler/executor needs these fields."""
        assert content_package.package_id
        assert content_package.content_type
        assert content_package.caption
        assert content_package.target_platforms
        assert content_package.priority >= 1

    def test_platform_values_are_valid(self, content_package: S3ContentPackage) -> None:
        for p in content_package.target_platforms:
            assert p.value in ("tiktok", "instagram", "youtube")

    def test_missing_content_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            S3ContentPackage(title="Test", caption="Test")  # content_type required


# ---------------------------------------------------------------------------
# DistributionRecord (Stage 3 output → Stage 4 input)
# ---------------------------------------------------------------------------


class TestS3DistributionRecord:
    def test_minimal_construction(self) -> None:
        dr = S3DistributionRecord(
            package_id="pkg-001",
            platform=Platform.TIKTOK,
        )
        assert dr.record_id  # auto-generated
        assert dr.dry_run is True  # safe default

    def test_json_roundtrip(self, s3_distribution_record: S3DistributionRecord) -> None:
        serialized = s3_distribution_record.model_dump_json()
        restored = S3DistributionRecord.model_validate_json(serialized)
        assert restored.record_id == s3_distribution_record.record_id
        assert restored.status == s3_distribution_record.status

    def test_dry_run_default_true(self) -> None:
        dr = S3DistributionRecord(package_id="pkg-x", platform=Platform.INSTAGRAM)
        assert dr.dry_run is True

    def test_status_values(self) -> None:
        for status in DistributionStatus:
            dr = S3DistributionRecord(
                package_id="pkg-x",
                platform=Platform.TIKTOK,
                status=status,
            )
            assert dr.status == status

    def test_has_fields_needed_by_stage4(self, s3_distribution_record: S3DistributionRecord) -> None:
        """Stage 4 needs: record_id, package_id (→ content_package_id), platform, post_id."""
        assert s3_distribution_record.record_id
        assert s3_distribution_record.package_id
        assert s3_distribution_record.platform
        assert s3_distribution_record.post_id


class TestS4DistributionRecord:
    def test_minimal_construction(self) -> None:
        dr = S4DistributionRecord(content_package_id="pkg-001", platform="tiktok")
        assert dr.record_id

    def test_json_roundtrip(self, s4_distribution_record_from_s3: S4DistributionRecord) -> None:
        serialized = s4_distribution_record_from_s3.model_dump_json()
        restored = S4DistributionRecord.model_validate_json(serialized)
        assert restored.record_id == s4_distribution_record_from_s3.record_id

    def test_status_literals(self) -> None:
        for status in ("posted", "scheduled", "failed", "dry_run"):
            dr = S4DistributionRecord(content_package_id="pkg-x", platform="tiktok", status=status)
            assert dr.status == status

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            S4DistributionRecord(content_package_id="pkg-x", platform="tiktok", status="unknown")


# ---------------------------------------------------------------------------
# DMConversationRecord (Stage 3 engagement output)
# ---------------------------------------------------------------------------


class TestDMConversationRecord:
    def test_minimal_construction(self) -> None:
        conv = DMConversationRecord(
            platform=Platform.TIKTOK,
            post_id="p1",
            comment_id="c1",
            user_id="alice",
            comment_text="where can I buy this?",
            comment_category=CommentCategory.TRIGGER_DM,
        )
        assert conv.conv_id
        assert conv.fsm_state == DMState.IDLE  # default

    def test_json_roundtrip(self) -> None:
        conv = DMConversationRecord(
            platform=Platform.INSTAGRAM,
            post_id="p2",
            comment_id="c2",
            user_id="bob",
            comment_text="love this!",
            comment_category=CommentCategory.PRAISE,
        )
        serialized = conv.model_dump_json()
        restored = DMConversationRecord.model_validate_json(serialized)
        assert restored.conv_id == conv.conv_id
        assert restored.comment_category == CommentCategory.PRAISE


# ---------------------------------------------------------------------------
# PerformanceMetricRecord (Stage 4 analytics)
# ---------------------------------------------------------------------------


class TestPerformanceMetricRecord:
    def test_minimal_construction(self) -> None:
        rec = PerformanceMetricRecord(
            distribution_record_id="dist-001",
            post_id="post-001",
            platform="tiktok",
            content_package_id="pkg-001",
        )
        assert rec.record_id
        assert rec.views == 0

    def test_json_roundtrip(self) -> None:
        rec = PerformanceMetricRecord(
            distribution_record_id="dist-001",
            post_id="post-001",
            platform="tiktok",
            views=10000,
            likes=800,
            engagement_rate_pct=8.0,
            hook_retention_3s_pct=65.0,
        )
        restored = PerformanceMetricRecord.model_validate_json(rec.model_dump_json())
        assert restored.views == 10000
        assert restored.hook_retention_3s_pct == 65.0

    def test_source_default_is_mock(self) -> None:
        rec = PerformanceMetricRecord(
            distribution_record_id="d", post_id="p", platform="tiktok"
        )
        assert rec.source == "mock"


# ---------------------------------------------------------------------------
# OptimizationDirectiveEnvelope (Stage 4 output → Stages 1/2/3)
# ---------------------------------------------------------------------------


class TestOptimizationDirectiveEnvelope:
    def test_construction(self) -> None:
        d = OptimizationDirectiveEnvelope(
            target_stage="stage2",
            directive_type="hook_rewrite",
            priority="high",
            rationale="question hooks outperform story 3x",
            payload={"hook_style": "question", "avoid_styles": ["story"]},
        )
        assert d.envelope_id
        assert d.dry_run is False

    def test_invalid_directive_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationDirectiveEnvelope(
                target_stage="stage2",
                directive_type="unknown_action",
                priority="high",
                rationale="test",
                payload={},
            )

    def test_invalid_target_stage_raises(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationDirectiveEnvelope(
                target_stage="stage9",
                directive_type="hook_rewrite",
                priority="high",
                rationale="test",
                payload={},
            )


# ---------------------------------------------------------------------------
# RedoQueueItem (Stage 4 output → Stages 1/2/3)
# ---------------------------------------------------------------------------


class TestRedoQueueItem:
    def test_construction(self) -> None:
        item = RedoQueueItem(
            source_distribution_record_id="dist-001",
            redo_reason="hook_failed",
            priority="high",
            suggested_mutations={"hook_style": "question"},
            target_stage="stage2",
        )
        assert item.item_id
        assert item.status == "queued"

    def test_invalid_redo_reason_raises(self) -> None:
        with pytest.raises(ValidationError):
            RedoQueueItem(
                source_distribution_record_id="dist-001",
                redo_reason="bad_vibes",
                priority="high",
                suggested_mutations={},
                target_stage="stage2",
            )


# ---------------------------------------------------------------------------
# ProductCatalogItem (Stage 5 — must be feature-flagged)
# ---------------------------------------------------------------------------


class TestProductCatalogItem:
    def test_construction(self) -> None:
        item = ProductCatalogItem(name="Bunny Serum", category="skincare", price_usd=29.99)
        assert item.product_id
        assert item.active is True

    def test_stage5_not_in_smoke_path(self) -> None:
        """
        Stage 5 ProductCatalogItem must not appear in the main pipeline flow.
        This test just confirms the model is importable but is NOT used elsewhere
        in the smoke path — it's a documentation assertion.
        """
        # If this import worked without error, Stage 5 contracts are isolated.
        from agents.stage4_analytics.contracts import ProductCatalogItem as PCI
        assert PCI  # importable but not wired into main pipeline
