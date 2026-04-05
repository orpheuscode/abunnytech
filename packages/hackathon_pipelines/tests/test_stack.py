from __future__ import annotations

import pytest
from PIL import Image

from hackathon_pipelines import build_dry_run_stack, build_runtime_stack
from hackathon_pipelines.adapters.live_api import VeoVideoGenerator
from hackathon_pipelines.contracts import GenerationBundle, TemplatePerformanceLabel
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
async def test_veo_dry_run_generates_local_mp4(tmp_path) -> None:
    product = tmp_path / "product.png"
    Image.new("RGB", (64, 64), color=(220, 120, 80)).save(product)
    avatar = tmp_path / "avatar.png"
    Image.new("RGB", (64, 64), color=(80, 120, 220)).save(avatar)
    bundle = GenerationBundle(
        bundle_id="bundle_1",
        template_id="tpl_1",
        product_id="prod_1",
        veo_prompt="Create a quick UGC reel.",
        product_title="Demo Camera",
        product_description="Compact camera for creators.",
        creative_brief="Show the avatar presenting the product.",
        product_image_path=str(product),
        avatar_image_path=str(avatar),
        reference_image_paths=[str(product), str(avatar)],
    )
    veo = VeoVideoGenerator(dry_run=True, output_dir=tmp_path / "videos")

    artifact = await veo.generate_ugc_video(bundle)

    assert artifact.video_path is not None
    assert artifact.video_path.endswith(".mp4")
    assert (tmp_path / "videos").exists()


@pytest.mark.asyncio
async def test_generation_bundle_includes_product_description_and_feedback_context(tmp_path) -> None:
    stack = build_dry_run_stack()
    await stack.orchestrator.run_reel_to_template_cycle()
    template = stack.templates.list_templates()[0]
    template.performance_label = TemplatePerformanceLabel.SUCCESSFUL_REUSE
    stack.templates.update_template(template)

    product = stack.products.top_by_score(limit=1)
    if not product:
        p = tmp_path / "product.png"
        p.write_bytes(b"fake")
        a = tmp_path / "avatar.png"
        a.write_bytes(b"fake")
        await stack.orchestrator.run_product_to_video(
            product_image_path=str(p),
            avatar_image_path=str(a),
        )
        product = stack.products.top_by_score(limit=1)

    p = tmp_path / "product2.png"
    p.write_bytes(b"fake")
    a = tmp_path / "avatar2.png"
    a.write_bytes(b"fake")
    bundle, _artifact = await stack.orchestrator._video.generate_for_product(  # type: ignore[attr-defined]
        template,
        product[0],
        product_image_path=str(p),
        avatar_image_path=str(a),
    )
    assert bundle.product_title == product[0].title
    assert bundle.product_description
    assert bundle.creative_brief
    assert "successful_reuse" in str(bundle.prior_template_metadata.get("performance_label"))


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
