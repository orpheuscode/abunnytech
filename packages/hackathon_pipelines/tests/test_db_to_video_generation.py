from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, VeoVideoGenerator
from hackathon_pipelines.contracts import (
    GenerationBundle,
    ProductCandidate,
    ReelSurfaceMetrics,
    VideoStructureRecord,
    VideoTemplateRecord,
)
from hackathon_pipelines.pipelines.db_to_video_generation import (
    ensure_templates_from_structures,
    generate_video_from_best_db_template,
    pick_best_template,
)
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore
from hackathon_pipelines.video_io import build_reference_collage_image


@pytest.mark.asyncio
async def test_ensure_templates_from_structures_creates_missing_templates(tmp_path: Path) -> None:
    store = SQLiteHackathonStore(tmp_path / "demo.sqlite3")
    store.upsert_reel_metrics(
        [
            ReelSurfaceMetrics(
                reel_id="reel_1",
                source_url="https://instagram.com/reel_1",
                likes=1000,
                comments=100,
            )
        ]
    )
    store.save_structure(
        VideoStructureRecord(
            record_id="struct_1",
            source_reel_id="reel_1",
            major_scenes=["hook"],
            hook_pattern="strong hook",
            raw_analysis_text="{}",
        )
    )

    created = await ensure_templates_from_structures(store, gemini=GeminiTemplateAgent(dry_run=True))

    assert len(created) == 1
    assert store.list_templates()


def test_pick_best_template_prefers_higher_source_engagement(tmp_path: Path) -> None:
    store = SQLiteHackathonStore(tmp_path / "demo.sqlite3")
    store.upsert_reel_metrics(
        [
            ReelSurfaceMetrics(reel_id="reel_low", source_url="https://instagram.com/low", likes=100, comments=10),
            ReelSurfaceMetrics(reel_id="reel_high", source_url="https://instagram.com/high", likes=5000, comments=400),
        ]
    )
    store.save_structure(
        VideoStructureRecord(
            record_id="struct_low",
            source_reel_id="reel_low",
            major_scenes=["a"],
            raw_analysis_text="{}",
        )
    )
    store.save_structure(
        VideoStructureRecord(
            record_id="struct_high",
            source_reel_id="reel_high",
            major_scenes=["b"],
            raw_analysis_text="{}",
        )
    )
    store.save_template(
        VideoTemplateRecord(template_id="tpl_low", structure_record_id="struct_low", veo_prompt_draft="low")
    )
    store.save_template(
        VideoTemplateRecord(template_id="tpl_high", structure_record_id="struct_high", veo_prompt_draft="high")
    )

    best = pick_best_template(store)

    assert best.template_id == "tpl_high"


@pytest.mark.asyncio
async def test_generate_video_from_best_db_template_creates_local_mp4(tmp_path: Path) -> None:
    store = SQLiteHackathonStore(tmp_path / "demo.sqlite3")
    store.upsert_reel_metrics(
        [
            ReelSurfaceMetrics(
                reel_id="reel_1",
                source_url="https://instagram.com/reel_1",
                likes=1200,
                comments=140,
            )
        ]
    )
    store.save_structure(
        VideoStructureRecord(
            record_id="struct_1",
            source_reel_id="reel_1",
            major_scenes=["hook", "demo"],
            hook_pattern="fast hook",
            raw_analysis_text="{}",
        )
    )

    avatar = tmp_path / "avatar.jpg"
    product = tmp_path / "product.jpg"
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)

    result = await generate_video_from_best_db_template(
        store,
        gemini=GeminiTemplateAgent(dry_run=True),
        veo=VeoVideoGenerator(dry_run=True, output_dir=tmp_path / "videos"),
        product_image_path=str(product),
        avatar_image_path=str(avatar),
    )

    assert result.template.template_id
    assert result.bundle.veo_prompt
    assert result.bundle.prompt_package.user_prompt
    assert Path(result.bundle.prompt_package.system_prompt_path).exists()
    assert Path(result.bundle.prompt_package.user_prompt_path).exists()
    assert Path(result.bundle.prompt_package.full_prompt_path).exists()
    assert (Path(result.bundle.prompt_package.artifact_dir) / "bundle.json").exists()
    assert result.bundle.generation_config.aspect_ratio == "9:16"
    assert result.bundle.generation_config.duration_seconds == 8
    assert result.artifact.video_path is not None
    assert Path(result.artifact.video_path).exists()


@pytest.mark.asyncio
async def test_generate_video_from_best_db_template_reuses_existing_templates_without_backfill(
    tmp_path: Path,
) -> None:
    store = SQLiteHackathonStore(tmp_path / "demo.sqlite3")
    store.upsert_reel_metrics(
        [ReelSurfaceMetrics(reel_id="reel_1", source_url="https://instagram.com/reel_1", likes=1200, comments=140)]
    )
    store.save_structure(
        VideoStructureRecord(
            record_id="struct_1",
            source_reel_id="reel_1",
            major_scenes=["hook", "demo"],
            hook_pattern="fast hook",
            raw_analysis_text="{}",
        )
    )
    store.save_structure(
        VideoStructureRecord(
            record_id="struct_2",
            source_reel_id="reel_1",
            major_scenes=["alt"],
            hook_pattern="alt hook",
            raw_analysis_text="{}",
        )
    )
    store.save_template(
        VideoTemplateRecord(
            template_id="tpl_existing",
            structure_record_id="struct_1",
            veo_prompt_draft="existing template",
        )
    )

    class FailingGemini:
        async def decide_template_disposition(self, structure, *, peer_templates):
            raise AssertionError("should not backfill templates when one already exists")

        async def build_generation_bundle(self, template, product, *, product_image_path, avatar_image_path):
            return GenerationBundle(
                bundle_id="bundle_existing",
                template_id=template.template_id,
                product_id=product.product_id,
                veo_prompt="Create a quick UGC reel.",
                product_title=product.title,
                product_description=product.notes or "",
                creative_brief="Reuse existing template.",
                product_image_path=product_image_path,
                avatar_image_path=avatar_image_path,
                reference_image_paths=[product_image_path, avatar_image_path],
            )

        async def build_instagram_post_draft(self, template, product, *, bundle, artifact, structure=None, metrics=None):
            raise AssertionError("not needed for this test")

    class FakeVeo:
        async def generate_ugc_video(self, bundle):
            return type("Artifact", (), {"artifact_id": "vid_x", "bundle_id": bundle.bundle_id, "video_uri": None, "video_path": str(tmp_path / "videos" / "out.mp4"), "model_id": "test", "reference_image_paths": bundle.reference_image_paths, "provider_metadata": {}})()

    avatar = tmp_path / "avatar.jpg"
    product = tmp_path / "product.jpg"
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "out.mp4").write_bytes(b"mp4")

    result = await generate_video_from_best_db_template(
        store,
        gemini=FailingGemini(),
        veo=FakeVeo(),
        product_image_path=str(product),
        avatar_image_path=str(avatar),
    )

    assert result.template.template_id == "tpl_existing"
    assert result.templates_created == 0


def test_build_reference_collage_image_uses_both_assets(tmp_path: Path) -> None:
    avatar = tmp_path / "avatar.jpg"
    product = tmp_path / "product.jpg"
    Image.new("RGB", (120, 120), color=(80, 120, 220)).save(avatar)
    Image.new("RGB", (120, 120), color=(220, 160, 60)).save(product)

    generated_bundle = GenerationBundle(
        bundle_id="bundle_1",
        template_id="tpl_1",
        product_id="prod_1",
        veo_prompt="Create a storefront video.",
        product_title="Camera",
        product_description="Compact creator camera.",
        creative_brief="Avatar introduces the camera in a short UGC reel.",
        avatar_image_path=str(avatar),
        product_image_path=str(product),
        reference_image_paths=[str(avatar), str(product)],
    )

    collage_path = build_reference_collage_image(
        bundle=generated_bundle,
        output_path=tmp_path / "reference.jpg",
    )

    assert collage_path.exists()
