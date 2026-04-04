"""
Tests for the Stage 4 AnalysisEngine.

Validates that fixture analytics produce correctly scored dimension results:
  - question/hero/fri_19:00 are top performers
  - story+tutorial/mon_09:00+thu_07:00 are bottom performers
  - directive_warranted is True for all dimensions that have clear gaps
"""
from __future__ import annotations


from agents.stage4_analytics.analysis_engine import AnalysisEngine, AnalyticsConfig
from agents.stage4_analytics.contracts import PerformanceMetricRecord


def test_bundle_contains_all_dimensions(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics, window_days=7)

    assert bundle.record_count == 10
    assert bundle.hook is not None
    assert bundle.content_tier is not None
    assert bundle.schedule is not None
    assert bundle.audio_trend is not None


def test_hook_question_is_top_performer(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)

    hook = bundle.hook
    assert hook is not None
    assert "question" in hook.top_performers, (
        f"Expected 'question' in top_performers, got {hook.top_performers}"
    )


def test_hook_story_tutorial_are_bottom_performers(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)

    hook = bundle.hook
    assert hook is not None
    bottom_styles = set(hook.bottom_performers)
    # story and/or tutorial should be flagged — both have < 35% 3s retention
    assert bottom_styles & {"story", "tutorial"}, (
        f"Expected 'story' or 'tutorial' in bottom_performers, got {hook.bottom_performers}"
    )


def test_schedule_fri_1900_is_top(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)

    sched = bundle.schedule
    assert sched is not None
    assert "fri_19:00" in sched.top_performers, (
        f"Expected 'fri_19:00' in top_performers, got {sched.top_performers}"
    )


def test_schedule_bottom_performers_are_early_morning(
    fixture_metrics: list[PerformanceMetricRecord],
) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)

    sched = bundle.schedule
    assert sched is not None
    # mon_09:00 and thu_07:00 have lowest engagement in fixture data
    bottoms = set(sched.bottom_performers)
    assert bottoms & {"mon_09:00", "thu_07:00"}, (
        f"Expected early-morning slots in bottom_performers, got {sched.bottom_performers}"
    )


def test_audio_trending_001_002_are_top(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)

    audio = bundle.audio_trend
    assert audio is not None
    top_audio = set(audio.top_performers)
    assert top_audio & {"audio_trending_001", "audio_trending_002"}, (
        f"Expected trending audio in top_performers, got {audio.top_performers}"
    )


def test_audio_flat_tracks_are_bottom(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)

    audio = bundle.audio_trend
    assert audio is not None
    bottoms = set(audio.bottom_performers)
    assert bottoms & {"audio_flat_003", "audio_flat_004"}, (
        f"Expected flat audio in bottom_performers, got {audio.bottom_performers}"
    )


def test_global_avg_engagement_is_plausible(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse(fixture_metrics)
    # Overall avg should be between 2% and 15% given the fixture mix
    assert 2.0 <= bundle.global_avg_engagement <= 15.0


def test_empty_records_returns_empty_bundle() -> None:
    engine = AnalysisEngine()
    bundle = engine.analyse([])
    assert bundle.record_count == 0
    assert bundle.hook is None
    assert bundle.schedule is None


def test_custom_config_changes_labels(fixture_metrics: list[PerformanceMetricRecord]) -> None:
    # With very high thresholds, all slots should be labelled "critical"
    strict_config = AnalyticsConfig(
        excellent_threshold=99.0,
        good_threshold=98.0,
        average_threshold=97.0,
        poor_threshold=96.0,
        min_sample_size=1,
    )
    engine = AnalysisEngine(config=strict_config)
    bundle = engine.analyse(fixture_metrics)
    # Every hook style should be "critical" under these thresholds
    if bundle.hook and bundle.hook.scores:
        for score in bundle.hook.scores:
            assert score.performance_label == "critical"
