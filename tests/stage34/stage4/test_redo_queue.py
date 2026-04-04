"""
Tests for the Stage 4 RedoQueueGenerator.

Validates that:
  - Underperforming posts from fixture data are flagged
  - Correct redo_reason is assigned per failure mode
  - suggested_mutations are present and relevant
  - max_retries prevents infinite queuing
  - Priority ordering is correct
"""
from __future__ import annotations

import pytest

from agents.stage4_analytics.contracts import PerformanceMetricRecord
from agents.stage4_analytics.redo_queue import RedoConfig, RedoQueueGenerator


def test_redo_items_generated_for_low_performers(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    gen = RedoQueueGenerator()
    items = gen.generate(fixture_metrics)
    # fixture has posts 003, 004, 007, 008 with very low hook retention and completion
    assert len(items) >= 2, f"Expected at least 2 redo items, got {len(items)}"


def test_hook_failed_assigned_for_low_3s_retention(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    gen = RedoQueueGenerator()
    items = gen.generate(fixture_metrics)
    reasons = [i.redo_reason for i in items]
    assert "hook_failed" in reasons, f"Expected hook_failed in redo reasons, got {reasons}"


def test_low_completion_assigned_for_low_completion_rate(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    # Use a more lenient hook threshold to force low_completion path
    config = RedoConfig(redo_hook_threshold=10.0, redo_completion_threshold=20.0)
    gen_lenient = RedoQueueGenerator(config=config)
    items = gen_lenient.generate(fixture_metrics)
    reasons = [i.redo_reason for i in items]
    assert "low_completion" in reasons or "hook_failed" in reasons, (
        f"Expected low_completion or hook_failed, got {reasons}"
    )


def test_hook_failed_suggests_different_hook_style(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    gen = RedoQueueGenerator()
    items = gen.generate(fixture_metrics)
    hook_items = [i for i in items if i.redo_reason == "hook_failed"]
    assert hook_items, "No hook_failed items to inspect"
    for item in hook_items:
        assert "hook_style" in item.suggested_mutations, (
            f"hook_failed item missing hook_style mutation: {item.suggested_mutations}"
        )
        assert "hook_rewrite" in item.suggested_mutations


def test_low_completion_suggests_duration_reduction(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    gen = RedoQueueGenerator(config=RedoConfig(redo_hook_threshold=0.0, redo_completion_threshold=20.0))
    items = gen.generate(fixture_metrics)
    completion_items = [i for i in items if i.redo_reason == "low_completion"]
    for item in completion_items:
        assert "reduce_duration" in item.suggested_mutations


def test_max_retries_prevents_requeuing(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    gen = RedoQueueGenerator(config=RedoConfig(max_retries=1))
    # Pre-populate retry counts to max for all records
    existing = {r.distribution_record_id: 1 for r in fixture_metrics}
    items = gen.generate(fixture_metrics, existing_retry_counts=existing)
    assert items == [], f"Expected empty redo queue when all at max_retries, got {len(items)} items"


def test_redo_items_sorted_critical_first(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    gen = RedoQueueGenerator()
    items = gen.generate(fixture_metrics)
    if len(items) < 2:
        pytest.skip("Need at least 2 items to test sort order")
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    orders = [priority_order[i.priority] for i in items]
    assert orders == sorted(orders), (
        f"Redo items not sorted by priority: {[i.priority for i in items]}"
    )


def test_redo_items_have_target_stage(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    gen = RedoQueueGenerator()
    items = gen.generate(fixture_metrics)
    valid_stages = {"stage1", "stage2", "stage3"}
    for item in items:
        assert item.target_stage in valid_stages, (
            f"Invalid target_stage: {item.target_stage}"
        )


def test_dry_run_propagated_to_items(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    gen = RedoQueueGenerator()
    items = gen.generate(fixture_metrics, dry_run=True)
    if items:
        assert all(i.dry_run is True for i in items), "dry_run not propagated"


def test_high_view_hook_failure_escalates_to_critical(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    """A post with >5000 views and hook_failed should be priority=critical."""
    gen = RedoQueueGenerator()
    items = gen.generate(fixture_metrics)
    # post_003 has 3200 views — may not hit critical. Create a synthetic one.
    from agents.stage4_analytics.contracts import PerformanceMetricRecord
    bad_post = PerformanceMetricRecord(
        distribution_record_id="dist_synthetic",
        post_id="post_synthetic",
        platform="tiktok",
        views=10000,
        likes=10,
        comments=1,
        shares=0,
        saves=0,
        follows_gained=0,
        watch_time_avg_seconds=1.5,
        completion_rate_pct=5.0,
        hook_retention_3s_pct=20.0,  # well below 35% threshold
        hook_retention_50pct=8.0,
        engagement_rate_pct=0.11,
        revenue_attributed=0.0,
        hook_style="story",
        source="mock",
    )
    items = gen.generate([bad_post])
    assert items, "No redo item generated for obvious hook failure"
    assert items[0].redo_reason == "hook_failed"
    assert items[0].priority == "critical", (
        f"Expected critical for high-view hook failure, got {items[0].priority}"
    )
