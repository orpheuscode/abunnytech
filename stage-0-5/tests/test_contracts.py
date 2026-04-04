"""Tests for the Pydantic v2 contracts."""

from __future__ import annotations

from packages.contracts.analytics import (
    MetricType,
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    RedoQueueItem,
    RedoReason,
)
from packages.contracts.base import Platform
from packages.contracts.content import (
    ContentPackage,
    ContentStatus,
    SceneBlock,
    VideoBlueprint,
)
from packages.contracts.discovery import (
    CompetitorWatchItem,
    TrainingMaterialsManifest,
    TrendingAudioItem,
)
from packages.contracts.distribution import DistributionRecord, DistributionStatus
from packages.contracts.identity import (
    AvatarProfile,
    ContentGuidelines,
    IdentityMatrix,
    PersonaArchetype,
    PlatformPresence,
    VoiceProfile,
)
from packages.contracts.monetization import (
    BrandOutreachRecord,
    DMConversationRecord,
    ProductCatalogItem,
)


class TestIdentityMatrix:
    def test_create_minimal(self):
        matrix = IdentityMatrix(name="Test", archetype=PersonaArchetype.EDUCATOR)
        assert matrix.name == "Test"
        assert matrix.archetype == PersonaArchetype.EDUCATOR
        assert matrix.id is not None
        assert matrix.ai_disclosure == "This content is AI-generated."

    def test_create_full(self):
        matrix = IdentityMatrix(
            name="Creator",
            archetype=PersonaArchetype.ENTERTAINER,
            tagline="Fun content",
            voice=VoiceProfile(voice_id="v1", provider="elevenlabs"),
            avatar=AvatarProfile(avatar_url="https://example.com/avatar.png"),
            guidelines=ContentGuidelines(topics=["tech", "AI"]),
            platforms=[PlatformPresence(platform=Platform.TIKTOK, handle="@test")],
        )
        assert len(matrix.platforms) == 1
        assert matrix.voice.voice_id == "v1"

    def test_audit_trail(self):
        matrix = IdentityMatrix(name="Test", archetype=PersonaArchetype.EDUCATOR)
        matrix.add_audit("test_action", actor="test")
        assert len(matrix.audit_log) == 1
        assert matrix.audit_log[0].action == "test_action"

    def test_serialization_roundtrip(self):
        matrix = IdentityMatrix(
            name="Roundtrip",
            archetype=PersonaArchetype.STORYTELLER,
            platforms=[PlatformPresence(platform=Platform.YOUTUBE, handle="@rt")],
        )
        data = matrix.model_dump(mode="json")
        restored = IdentityMatrix.model_validate(data)
        assert restored.name == "Roundtrip"
        assert str(restored.id) == str(matrix.id)


class TestDiscoveryContracts:
    def test_trending_audio(self):
        item = TrendingAudioItem(
            platform=Platform.TIKTOK,
            audio_id="a123",
            title="Viral Sound",
            usage_count=50000,
        )
        assert item.platform == Platform.TIKTOK
        assert item.usage_count == 50000

    def test_competitor_watch(self):
        item = CompetitorWatchItem(
            platform=Platform.INSTAGRAM,
            account_handle="@rival",
            follower_count=100000,
        )
        assert item.follower_count == 100000

    def test_training_manifest(self):
        manifest = TrainingMaterialsManifest(
            identity_id="test-id",
            analysis_summary="Test analysis",
        )
        assert manifest.identity_id == "test-id"


class TestContentContracts:
    def test_video_blueprint(self):
        bp = VideoBlueprint(
            identity_id="test",
            title="Test Video",
            scenes=[SceneBlock(order=1, narration_text="Hello")],
        )
        assert len(bp.scenes) == 1
        assert bp.status == ContentStatus.DRAFT

    def test_content_package(self):
        pkg = ContentPackage(
            identity_id="test",
            blueprint_id="bp-1",
            title="Test Package",
        )
        assert pkg.status == ContentStatus.RENDERED


class TestDistributionContracts:
    def test_distribution_record(self):
        rec = DistributionRecord(
            content_package_id="pkg-1",
            identity_id="id-1",
            platform=Platform.TIKTOK,
        )
        assert rec.dry_run is True
        assert rec.status == DistributionStatus.QUEUED


class TestAnalyticsContracts:
    def test_metric_record(self):
        m = PerformanceMetricRecord(
            distribution_record_id="d-1",
            identity_id="id-1",
            platform=Platform.TIKTOK,
            metric_type=MetricType.VIEWS,
            value=1200,
        )
        assert m.value == 1200

    def test_optimization_envelope(self):
        env = OptimizationDirectiveEnvelope(identity_id="id-1")
        assert len(env.directives) == 0

    def test_redo_item(self):
        item = RedoQueueItem(
            identity_id="id-1",
            target_stage=2,
            reason=RedoReason.LOW_ENGAGEMENT,
        )
        assert item.processed is False


class TestMonetizationContracts:
    def test_product_catalog(self):
        product = ProductCatalogItem(
            identity_id="id-1",
            name="AI Course",
            price=29.99,
        )
        assert product.active is True

    def test_brand_outreach(self):
        rec = BrandOutreachRecord(
            identity_id="id-1",
            brand_name="TechBrand",
        )
        assert rec.status == "identified"

    def test_dm_record(self):
        dm = DMConversationRecord(
            identity_id="id-1",
            platform=Platform.INSTAGRAM,
            counterparty_handle="@brand",
        )
        assert dm.direction == "outbound"
