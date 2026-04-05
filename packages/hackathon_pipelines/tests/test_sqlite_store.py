from __future__ import annotations

from pathlib import Path

from hackathon_pipelines.contracts import (
    PostAnalyticsSnapshot,
    ProductCandidate,
    ReelSurfaceMetrics,
    TemplateDisposition,
    TemplatePerformanceLabel,
    VideoStructureRecord,
    VideoTemplateRecord,
)
from hackathon_pipelines.stores import (
    SQLiteAnalyticsSink,
    SQLiteHackathonStore,
    SQLiteProductCatalog,
    SQLiteReelSink,
    SQLiteTemplateStore,
)


def test_sqlite_hackathon_store_round_trips(tmp_path: Path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    store = SQLiteHackathonStore(db_path)

    reel = ReelSurfaceMetrics(
        reel_id="reel_1",
        source_url="https://instagram.com/reel_1",
        views=12_500,
        likes=740,
        comments=63,
    )
    store.upsert_reel_metrics([reel])
    assert store.get_reel_metric("reel_1") is not None
    assert store.get_reel_metric("reel_1").views == 12_500

    updated_reel = reel.model_copy(update={"views": 18_000, "likes": 900})
    store.upsert_reel_metrics([updated_reel])
    assert store.list_reel_metrics()[0].views == 18_000

    structure = VideoStructureRecord(
        record_id="struct_1",
        source_reel_id="reel_1",
        major_scenes=["hook", "demo", "cta"],
        hook_pattern="fast hook",
        audio_music_cues="bass-heavy",
        visual_style="ugc",
        sequence_description="open -> demo -> close",
        on_screen_text_notes="big captions",
        raw_analysis_text='{"ok":true}',
    )
    store.save_structure(structure)
    assert store.get_structure("struct_1") is not None
    assert store.get_structure("struct_1").major_scenes == ["hook", "demo", "cta"]

    template = VideoTemplateRecord(
        template_id="tpl_1",
        structure_record_id="struct_1",
        veo_prompt_draft="Use a fast hook and clear product showcase.",
        disposition=TemplateDisposition.ITERATE,
    )
    store.save_template(template)
    assert store.get_template("tpl_1") is not None
    assert store.get_template("tpl_1").disposition == TemplateDisposition.ITERATE

    updated_template = template.model_copy(
        update={"performance_label": TemplatePerformanceLabel.SUCCESSFUL_REUSE}
    )
    store.update_template(updated_template)

    candidates = [
        ProductCandidate(
            product_id="prod_low",
            title="Low",
            source_url="https://example.com/low",
            dropship_score=0.25,
        ),
        ProductCandidate(
            product_id="prod_high",
            title="High",
            source_url="https://example.com/high",
            dropship_score=0.92,
        ),
        ProductCandidate(
            product_id="prod_mid",
            title="Mid",
            source_url="https://example.com/mid",
            dropship_score=0.61,
        ),
    ]
    store.upsert_candidates(candidates)
    assert [candidate.product_id for candidate in store.top_candidates(limit=3)] == [
        "prod_high",
        "prod_mid",
        "prod_low",
    ]

    snapshot = PostAnalyticsSnapshot(
        snapshot_id="snap_1",
        post_id="post_1",
        views=9_000,
        likes=450,
        comments=31,
        engagement_trend="rising",
    )
    store.persist_post_analytics(snapshot)
    assert store.get_snapshot("snap_1") is not None
    assert store.get_snapshot("snap_1").likes == 450

    reopened = SQLiteHackathonStore(db_path)
    assert reopened.get_reel_metric("reel_1").views == 18_000
    assert reopened.get_structure("struct_1").source_reel_id == "reel_1"
    assert reopened.get_template("tpl_1").performance_label == TemplatePerformanceLabel.SUCCESSFUL_REUSE
    assert reopened.get_candidate("prod_high").dropship_score == 0.92
    assert reopened.get_snapshot("snap_1").engagement_trend == "rising"


def test_sqlite_port_adapters_share_one_database(tmp_path: Path) -> None:
    db_path = tmp_path / "shared.sqlite3"

    reel_sink = SQLiteReelSink(db_path)
    template_store = SQLiteTemplateStore(db_path)
    product_catalog = SQLiteProductCatalog(db_path)
    analytics_sink = SQLiteAnalyticsSink(db_path)

    reel_sink.persist_reel_metrics(
        [
            ReelSurfaceMetrics(
                reel_id="reel_a",
                source_url="https://instagram.com/a",
                views=20_000,
                likes=900,
                comments=80,
            )
        ]
    )
    template_store.save_structure(
        VideoStructureRecord(
            record_id="struct_a",
            source_reel_id="reel_a",
            major_scenes=["scene_a"],
            hook_pattern="hook_a",
            raw_analysis_text="{}",
        )
    )
    template_store.save_template(
        VideoTemplateRecord(
            template_id="tpl_a",
            structure_record_id="struct_a",
            veo_prompt_draft="prompt a",
        )
    )
    product_catalog.upsert_candidates(
        [
            ProductCandidate(product_id="prod_a", title="A", source_url="https://example.com/a", dropship_score=0.8),
            ProductCandidate(product_id="prod_b", title="B", source_url="https://example.com/b", dropship_score=0.3),
        ]
    )
    analytics_sink.persist_post_analytics(
        PostAnalyticsSnapshot(snapshot_id="snap_a", post_id="post_a", views=13_000, likes=510, comments=22)
    )

    reopened = SQLiteHackathonStore(db_path)
    assert reopened.list_reel_metrics()[0].reel_id == "reel_a"
    assert reopened.list_templates()[0].template_id == "tpl_a"
    assert reopened.top_candidates(limit=1)[0].product_id == "prod_a"
    assert reopened.list_snapshots()[0].post_id == "post_a"
