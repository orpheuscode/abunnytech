"""
Tests for the Stage 4 DirectiveGenerator.

Validates that:
  - Fixture data produces directives for hook, schedule, and audio dimensions
  - Directive payloads are correctly structured for the target stage
  - Directives are sorted by priority (critical first)
  - dry_run flag is propagated to all directives
"""
from __future__ import annotations


from agents.stage4_analytics.analysis_engine import AnalysisEngine
from agents.stage4_analytics.contracts import PerformanceMetricRecord
from agents.stage4_analytics.directive_generator import DirectiveGenerator


def test_directives_produced_for_fixture_data(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    directives = gen.generate(bundle)

    assert len(directives) >= 2, (
        f"Expected at least 2 directives from fixture data, got {len(directives)}"
    )


def test_hook_rewrite_directive_present(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    directives = gen.generate(bundle)

    types = [d.directive_type for d in directives]
    assert "hook_rewrite" in types, f"Expected hook_rewrite directive, got {types}"


def test_hook_rewrite_targets_stage2(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    hook_directives = [d for d in gen.generate(bundle) if d.directive_type == "hook_rewrite"]

    assert hook_directives, "No hook_rewrite directives"
    for d in hook_directives:
        assert d.target_stage == "stage2", f"hook_rewrite should target stage2, got {d.target_stage}"


def test_hook_rewrite_payload_structure(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    hook_d = next(d for d in gen.generate(bundle) if d.directive_type == "hook_rewrite")

    payload = hook_d.payload
    assert "hook_style" in payload
    assert "avoid_styles" in payload
    assert isinstance(payload["avoid_styles"], list)
    assert "target_3s_retention_pct" in payload


def test_schedule_shift_directive_targets_stage3(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    sched_directives = [d for d in gen.generate(bundle) if d.directive_type == "schedule_shift"]

    assert sched_directives, "No schedule_shift directives from fixture data"
    for d in sched_directives:
        assert d.target_stage == "stage3", f"schedule_shift should target stage3, got {d.target_stage}"


def test_schedule_shift_payload_has_lift_pct(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    sched_d = next(d for d in gen.generate(bundle) if d.directive_type == "schedule_shift")

    assert "lift_pct" in sched_d.payload
    assert sched_d.payload["lift_pct"] >= 0


def test_audio_swap_directive_present(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    audio_directives = [d for d in gen.generate(bundle) if d.directive_type == "audio_swap"]

    assert audio_directives, "No audio_swap directives from fixture data"


def test_audio_swap_payload_lists_avoid_and_preferred(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    audio_d = next(d for d in gen.generate(bundle) if d.directive_type == "audio_swap")

    assert "avoid_audio_ids" in audio_d.payload
    assert "preferred_audio_ids" in audio_d.payload
    assert isinstance(audio_d.payload["avoid_audio_ids"], list)
    assert isinstance(audio_d.payload["preferred_audio_ids"], list)
    # Flat audio should be in avoid list
    avoid = audio_d.payload["avoid_audio_ids"]
    assert any("flat" in aid for aid in avoid), f"Expected flat audio in avoid list: {avoid}"


def test_directives_sorted_by_priority(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    directives = gen.generate(bundle)

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    orders = [priority_order[d.priority] for d in directives]
    assert orders == sorted(orders), f"Directives not sorted by priority: {[d.priority for d in directives]}"


def test_dry_run_propagated(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    directives = gen.generate(bundle, dry_run=True)

    assert all(d.dry_run is True for d in directives), "dry_run not propagated to all directives"


def test_directives_have_valid_envelope_ids(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    gen = DirectiveGenerator()
    directives = gen.generate(bundle)

    ids = [d.envelope_id for d in directives]
    # All IDs should be unique
    assert len(ids) == len(set(ids)), "Duplicate envelope_ids found"
    # All should be non-empty strings
    assert all(ids), "Some envelope_ids are empty"


def test_no_directives_on_empty_bundle() -> None:
    from agents.stage4_analytics.models import AnalysisBundle
    gen = DirectiveGenerator()
    directives = gen.generate(AnalysisBundle(window_days=7, record_count=0))
    assert directives == []
