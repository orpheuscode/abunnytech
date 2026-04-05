from __future__ import annotations

from hackathon_pipelines.prototype_bridge import LOCKED_REFERENCE_VEO_SYSTEM_PROMPT
from integration.browser_use_veo31_snippets import (
    build_manual_generation_bundle,
    guess_mime_type,
    run_demo_local_generation,
)
from PIL import Image


def test_build_manual_generation_bundle_includes_both_reference_images() -> None:
    bundle = build_manual_generation_bundle(
        avatar_image_path="avatars/model.png",
        product_image_path="products/item.png",
        prompt="Make a vertical storefront video.",
    )
    assert bundle.avatar_image_path == "avatars/model.png"
    assert bundle.product_image_path == "products/item.png"
    assert bundle.reference_image_paths == ["avatars/model.png", "products/item.png"]
    assert "Make a vertical storefront video." in bundle.veo_prompt
    assert LOCKED_REFERENCE_VEO_SYSTEM_PROMPT.splitlines()[0] in bundle.veo_prompt
    assert bundle.product_description
    assert bundle.creative_brief == "Make a vertical storefront video."


def test_guess_mime_type_defaults_for_png() -> None:
    assert guess_mime_type("avatar.png") == "image/png"


async def test_run_demo_local_generation_creates_mp4(tmp_path) -> None:
    avatar = tmp_path / "avatar.png"
    product = tmp_path / "product.png"
    Image.new("RGB", (80, 80), color=(40, 140, 220)).save(avatar)
    Image.new("RGB", (80, 80), color=(220, 160, 60)).save(product)

    artifact = await run_demo_local_generation(
        avatar_image_path=str(avatar),
        product_image_path=str(product),
        prompt="Create a quick storefront reel.",
        output_dir=tmp_path / "videos",
    )

    assert artifact.video_path is not None
    assert artifact.video_path.endswith(".mp4")
