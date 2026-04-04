"""
Stage handoff validation tests — m2t4.

Tests that the contracts at each stage boundary are compatible:
  - Stage 0 → Stage 1  (IdentityMatrix feeds discovery)
  - Stage 1 → Stage 2  (VideoBlueprint feeds generation)
  - Stage 2 → Stage 3  (ContentPackage feeds distribution)
  - Stage 3 → Stage 4  (DistributionRecord feeds analytics)

Also validates:
  - Feature flags respected (Stage 5 is gated)
  - Dry-run mode propagates correctly
  - No live credentials required in any smoke path
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from packages.evals.fixtures import (
    adapt_s3_to_s4_distribution_record,
    make_content_package,
    make_identity,
    make_s3_distribution_record,
    make_video_blueprint,
)
from packages.evals.validators import (
    assert_contract_valid,
    assert_feature_flag_off,
    assert_no_live_credentials,
)

from agents.stage3_distribution.contracts import (
    DistributionRecord as S3DistributionRecord,
    DistributionStatus,
    IdentityMatrix,
    Platform as S3Platform,
)
from agents.stage4_analytics.contracts import (
    DistributionRecord as S4DistributionRecord,
    VideoBlueprint,
)
from agents.stage4_analytics.state_adapter import StateAdapter


# ---------------------------------------------------------------------------
# Handoff: Stage 0 → Stage 1
# IdentityMatrix is produced by Stage 0; Stage 1 uses it to scope trending
# discovery (niche tags, platform targets, audio style).
# ---------------------------------------------------------------------------


class TestS0ToS1Handoff:
    def test_identity_provides_niche_for_discovery(self, identity: IdentityMatrix) -> None:
        assert identity.niche, "Stage 1 requires niche to scope trending searches"

    def test_identity_provides_target_platforms(self, identity: IdentityMatrix) -> None:
        assert identity.target_platforms, "Stage 1 needs target_platforms for per-platform trending fetch"

    def test_identity_provides_persona_for_audio_style(self, identity: IdentityMatrix) -> None:
        # voice_tags shape the audio discovery queries
        assert isinstance(identity.voice_tags, list)

    def test_identity_id_is_stable_across_serialization(self, identity: IdentityMatrix) -> None:
        restored = IdentityMatrix.model_validate_json(identity.model_dump_json())
        assert restored.identity_id == identity.identity_id

    def test_identity_feeds_blueprint_generation_context(
        self, identity: IdentityMatrix, video_blueprint: VideoBlueprint
    ) -> None:
        # A blueprint generated from this identity's context should carry the same niche
        assert identity.niche  # blueprint.topic should relate to this
        assert video_blueprint.niche_tags  # populated from identity.niche at generation time


# ---------------------------------------------------------------------------
# Handoff: Stage 1 → Stage 2
# VideoBlueprint (+ TrendingAudioItem) is produced by Stage 1 and consumed
# by Stage 2 to generate a ContentPackage.
# ---------------------------------------------------------------------------


class TestS1ToS2Handoff:
    def test_blueprint_has_hook_style(self, video_blueprint: VideoBlueprint) -> None:
        assert video_blueprint.hook_style, "Stage 2 needs hook_style to write the opening line"

    def test_blueprint_has_duration(self, video_blueprint: VideoBlueprint) -> None:
        assert video_blueprint.duration_seconds > 0

    def test_blueprint_has_topic(self, video_blueprint: VideoBlueprint) -> None:
        assert video_blueprint.topic, "Stage 2 needs topic to generate script content"

    def test_blueprint_id_carried_into_package(
        self, video_blueprint: VideoBlueprint
    ) -> None:
        # Simulate Stage 2: create a package referencing the blueprint
        pkg = make_content_package(blueprint_id=video_blueprint.blueprint_id)
        assert pkg.blueprint_id == video_blueprint.blueprint_id

    def test_blueprint_niche_tags_scope_content(self, video_blueprint: VideoBlueprint) -> None:
        assert isinstance(video_blueprint.niche_tags, list)


# ---------------------------------------------------------------------------
# Handoff: Stage 2 → Stage 3
# ContentPackage is produced by Stage 2 and fed to Stage 3's scheduler.
# ---------------------------------------------------------------------------


class TestS2ToS3Handoff:
    def test_package_has_caption(self, content_package) -> None:
        assert content_package.caption, "Stage 3 executor appends ai_disclosure to this"

    def test_package_has_target_platforms(self, content_package) -> None:
        assert content_package.target_platforms, "Stage 3 scheduler routes by platform"

    def test_package_has_priority(self, content_package) -> None:
        assert content_package.priority >= 1, "Stage 3 scheduler queues by priority"

    def test_package_has_identity_id(self, content_package) -> None:
        assert content_package.identity_id, "Stage 3 executor loads identity for disclosure footer"

    def test_package_blueprint_id_traceability(self, content_package) -> None:
        assert content_package.blueprint_id, "Needed to link DistributionRecord back to Stage 1/2"

    def test_scheduler_accepts_package(self, content_package) -> None:
        from agents.stage3_distribution.scheduler import (
            PlatformTarget,
            PostingScheduler,
            PostingWindow,
        )
        scheduler = PostingScheduler(
            targets=[
                PlatformTarget(
                    platform=S3Platform.TIKTOK,
                    window=PostingWindow(start_hour=0, end_hour=23),
                    max_posts_per_day=3,
                )
            ],
            dry_run=True,
            sandbox=True,
        )
        posts = scheduler.enqueue(content_package)
        assert len(posts) >= 1, "Scheduler should enqueue at least one post"
        for post in posts:
            assert post.package.package_id == content_package.package_id

    @pytest.mark.asyncio
    async def test_executor_produces_distribution_record(self, content_package, identity) -> None:
        from unittest.mock import MagicMock
        from browser_runtime.types import ProviderType
        from agents.stage3_distribution.adapters.mock import MockPlatformAdapter
        from agents.stage3_distribution.executor import PostingExecutor
        from agents.stage3_distribution.scheduler import (
            PlatformTarget,
            PostingScheduler,
            PostingWindow,
        )

        mock_provider = MagicMock()
        mock_provider.provider_type = ProviderType.MOCK
        adapter = MockPlatformAdapter(provider=mock_provider, dry_run=True)
        executor = PostingExecutor(adapter=adapter, dry_run=True)

        scheduler = PostingScheduler(
            targets=[
                PlatformTarget(
                    platform=S3Platform.TIKTOK,
                    window=PostingWindow(start_hour=0, end_hour=23),
                    max_posts_per_day=3,
                )
            ],
            dry_run=True,
            sandbox=True,
        )
        scheduler.enqueue(content_package)
        posts = scheduler.dequeue_ready()
        assert posts

        record = await executor.execute_post(posts[0], identity)
        assert record.record_id
        assert record.package_id == content_package.package_id
        assert record.dry_run is True
        assert record.status == DistributionStatus.DRY_RUN


# ---------------------------------------------------------------------------
# Handoff: Stage 3 → Stage 4
# DistributionRecord produced by Stage 3 must map cleanly to Stage 4's schema.
# ---------------------------------------------------------------------------


class TestS3ToS4Handoff:
    def test_s3_record_adapts_to_s4_schema(
        self, s3_distribution_record: S3DistributionRecord
    ) -> None:
        s4 = adapt_s3_to_s4_distribution_record(s3_distribution_record)
        assert s4.record_id == s3_distribution_record.record_id
        assert s4.content_package_id == s3_distribution_record.package_id
        assert s4.platform == s3_distribution_record.platform.value

    def test_s3_status_maps_to_s4_status(self) -> None:
        """All Stage 3 status values must map to valid Stage 4 literals."""
        from packages.evals.fixtures import _STATUS_MAP
        from agents.stage4_analytics.contracts import DistributionRecord as S4DR
        import pydantic

        for s3_status, s4_status in _STATUS_MAP.items():
            # Should not raise a validation error
            dr = S4DR(
                content_package_id="pkg-x",
                platform="tiktok",
                status=s4_status,
            )
            assert dr.status == s4_status

    @pytest.mark.asyncio
    async def test_s4_runner_accepts_adapted_record(
        self,
        s4_distribution_record_from_s3: S4DistributionRecord,
        tmp_state_adapter: StateAdapter,
    ) -> None:
        from agents.stage4_analytics.runner import Stage4Runner

        runner = Stage4Runner(
            dry_run=True,
            state_adapter=tmp_state_adapter,
        )
        result = await runner.run([s4_distribution_record_from_s3])
        # With a single dry_run record, metrics may be sparse — but the pipeline runs.
        assert result is not None
        assert result.dry_run is True
        assert isinstance(result.metrics, list)
        assert isinstance(result.directives, list)
        assert isinstance(result.redo_items, list)

    @pytest.mark.asyncio
    async def test_s4_runner_with_fixture_records_produces_directives(
        self,
        s4_distribution_records: list[S4DistributionRecord],
        tmp_state_adapter: StateAdapter,
    ) -> None:
        """10-post fixture should produce at least one directive and one redo item."""
        from agents.stage4_analytics.runner import Stage4Runner
        fixture_path = str(
            Path(__file__).parents[0] / "stage4" / "fixtures" / "sample_analytics.json"
        )
        runner = Stage4Runner(
            dry_run=True,
            state_adapter=tmp_state_adapter,
            fixture_path=fixture_path,
        )
        result = await runner.run(s4_distribution_records)
        assert len(result.metrics) == 10
        assert len(result.directives) >= 1, "10-post fixture should trigger at least one directive"
        assert len(result.redo_items) >= 1, "Low-performing posts should appear in redo queue"

    @pytest.mark.asyncio
    async def test_directives_have_valid_target_stages(
        self,
        s4_distribution_records: list[S4DistributionRecord],
        tmp_state_adapter: StateAdapter,
    ) -> None:
        from agents.stage4_analytics.runner import Stage4Runner
        fixture_path = str(
            Path(__file__).parents[0] / "stage4" / "fixtures" / "sample_analytics.json"
        )
        runner = Stage4Runner(
            dry_run=True,
            state_adapter=tmp_state_adapter,
            fixture_path=fixture_path,
        )
        result = await runner.run(s4_distribution_records)
        valid_stages = {"stage1", "stage2", "stage3", "stage1+stage2"}
        for d in result.directives:
            assert d.target_stage in valid_stages, (
                f"Directive {d.directive_type} has invalid target_stage={d.target_stage!r}"
            )

    @pytest.mark.asyncio
    async def test_redo_items_target_valid_stages(
        self,
        s4_distribution_records: list[S4DistributionRecord],
        tmp_state_adapter: StateAdapter,
    ) -> None:
        from agents.stage4_analytics.runner import Stage4Runner
        fixture_path = str(
            Path(__file__).parents[0] / "stage4" / "fixtures" / "sample_analytics.json"
        )
        runner = Stage4Runner(
            dry_run=True,
            state_adapter=tmp_state_adapter,
            fixture_path=fixture_path,
        )
        result = await runner.run(s4_distribution_records)
        for item in result.redo_items:
            assert item.target_stage in ("stage1", "stage2", "stage3")

    @pytest.mark.asyncio
    async def test_directives_persisted_to_adapter(
        self,
        s4_distribution_records: list[S4DistributionRecord],
        tmp_state_adapter: StateAdapter,
    ) -> None:
        from agents.stage4_analytics.runner import Stage4Runner
        fixture_path = str(
            Path(__file__).parents[0] / "stage4" / "fixtures" / "sample_analytics.json"
        )
        runner = Stage4Runner(
            dry_run=True,
            state_adapter=tmp_state_adapter,
            fixture_path=fixture_path,
        )
        result = await runner.run(s4_distribution_records)
        stored = tmp_state_adapter.load_directives()
        assert len(stored) == len(result.directives)


# ---------------------------------------------------------------------------
# Feature flag sanity checks
# ---------------------------------------------------------------------------


class TestFeatureFlags:
    def test_stage5_monetize_flag_off_by_default(self) -> None:
        assert_feature_flag_off(dict(os.environ), "STAGE5_MONETIZE_ENABLED")

    def test_no_live_credentials_in_environment(self) -> None:
        assert_no_live_credentials(dict(os.environ))

    def test_shopify_adapter_not_in_main_pipeline(self) -> None:
        """
        Stage 3 executor must not import ShopifyAdapter directly.
        The adapter is only safe to use when stage5_monetize feature flag is on.
        """
        import ast
        executor_path = Path(__file__).parents[1] / "agents" / "stage3_distribution" / "executor.py"
        source = executor_path.read_text(encoding="utf-8")
        assert "ShopifyAdapter" not in source, (
            "ShopifyAdapter must not be imported in stage3 executor — it is Stage 5 only."
        )

    def test_browser_dry_run_default_is_true(self) -> None:
        from browser_runtime.config import BrowserRuntimeSettings
        settings = BrowserRuntimeSettings()
        assert settings.dry_run is True, (
            "BROWSER_DRY_RUN must default to True so smoke runs never make live posts."
        )

    def test_global_kill_switch_default_is_off(self) -> None:
        from browser_runtime.config import BrowserRuntimeSettings
        settings = BrowserRuntimeSettings()
        assert settings.global_kill_switch.enabled is False


# ---------------------------------------------------------------------------
# Dry-run propagation
# ---------------------------------------------------------------------------


class TestDryRunPropagation:
    @pytest.mark.asyncio
    async def test_stage3_executor_marks_records_dry_run(
        self, content_package, identity
    ) -> None:
        from browser_runtime.types import ProviderType
        from agents.stage3_distribution.adapters.mock import MockPlatformAdapter
        from agents.stage3_distribution.executor import PostingExecutor
        from agents.stage3_distribution.scheduler import (
            PlatformTarget,
            PostingScheduler,
            PostingWindow,
        )

        mock_provider = MagicMock()
        mock_provider.provider_type = ProviderType.MOCK
        executor = PostingExecutor(
            adapter=MockPlatformAdapter(provider=mock_provider, dry_run=True),
            dry_run=True,
        )
        scheduler = PostingScheduler(
            targets=[
                PlatformTarget(
                    platform=S3Platform.TIKTOK,
                    window=PostingWindow(start_hour=0, end_hour=23),
                    max_posts_per_day=3,
                )
            ],
            dry_run=True,
            sandbox=True,
        )
        scheduler.enqueue(content_package)
        for post in scheduler.dequeue_ready():
            record = await executor.execute_post(post, identity)
            assert record.dry_run is True
            assert record.status == DistributionStatus.DRY_RUN

    @pytest.mark.asyncio
    async def test_stage4_runner_dry_run_flag_propagates(
        self,
        s4_distribution_records: list[S4DistributionRecord],
        tmp_state_adapter: StateAdapter,
    ) -> None:
        from agents.stage4_analytics.runner import Stage4Runner
        fixture_path = str(
            Path(__file__).parents[0] / "stage4" / "fixtures" / "sample_analytics.json"
        )
        runner = Stage4Runner(
            dry_run=True,
            state_adapter=tmp_state_adapter,
            fixture_path=fixture_path,
        )
        result = await runner.run(s4_distribution_records)
        assert result.dry_run is True
        for directive in result.directives:
            assert directive.dry_run is True
        for item in result.redo_items:
            assert item.dry_run is True
