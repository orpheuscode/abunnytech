from __future__ import annotations

import pytest

from hackathon_pipelines import build_dry_run_stack, build_runtime_stack
from hackathon_pipelines.stores import SQLiteHackathonStore


@pytest.mark.asyncio
async def test_reel_discovery_creates_template() -> None:
    stack = build_dry_run_stack()
    summary = await stack.orchestrator.run_reel_to_template_cycle()
    assert summary.templates_created >= 1
    assert stack.templates.list_templates()


@pytest.mark.asyncio
async def test_product_to_video_dry_run(tmp_path) -> None:
    stack = build_dry_run_stack()
    p = tmp_path / "product.png"
    p.write_bytes(b"fake")
    a = tmp_path / "avatar.png"
    a.write_bytes(b"fake")
    summary = await stack.orchestrator.run_product_to_video(
        product_image_path=str(p),
        avatar_image_path=str(a),
    )
    assert summary.generations == 1


@pytest.mark.asyncio
async def test_publish_and_feedback_updates_template(tmp_path) -> None:
    stack = build_dry_run_stack()
    await stack.orchestrator.run_reel_to_template_cycle()
    tpl = stack.templates.list_templates()[0]
    v = tmp_path / "out.mp4"
    v.write_bytes(b"")
    summary = await stack.orchestrator.run_publish_and_feedback(
        media_path=str(v),
        caption="Test #hackathon",
        template_id=tpl.template_id,
        dry_run=True,
    )
    assert summary.posts == 1
    assert stack.analytics.snapshots
    updated = stack.templates.get_template(tpl.template_id)
    assert updated is not None
    assert updated.performance_label is not None


@pytest.mark.asyncio
async def test_closed_loop_cycle_dry_run(tmp_path) -> None:
    stack = build_dry_run_stack()
    p = tmp_path / "product.png"
    p.write_bytes(b"fake")
    a = tmp_path / "avatar.png"
    a.write_bytes(b"fake")
    m = tmp_path / "generated.mp4"
    summary = await stack.orchestrator.run_closed_loop_cycle(
        product_image_path=str(p),
        avatar_image_path=str(a),
        media_path=str(m),
        dry_run=True,
    )
    assert summary.reel_summary.templates_created >= 1
    assert summary.product_summary.generations == 1
    assert summary.publish_summary is not None
    assert summary.publish_summary.posts == 1
    assert summary.template_id is not None


@pytest.mark.asyncio
async def test_runtime_stack_persists_to_sqlite(tmp_path) -> None:
    db_path = tmp_path / "hackathon.sqlite3"
    stack = build_runtime_stack(dry_run=True, db_path=db_path)
    p = tmp_path / "product.png"
    p.write_bytes(b"fake")
    a = tmp_path / "avatar.png"
    a.write_bytes(b"fake")
    m = tmp_path / "generated.mp4"
    await stack.orchestrator.run_closed_loop_cycle(
        product_image_path=str(p),
        avatar_image_path=str(a),
        media_path=str(m),
        dry_run=True,
    )

    reopened = SQLiteHackathonStore(db_path)
    assert reopened.list_templates()
    assert reopened.top_candidates(limit=1)
    assert reopened.list_snapshots()
