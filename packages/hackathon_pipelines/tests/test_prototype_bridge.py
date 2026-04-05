from __future__ import annotations

from pathlib import Path

from hackathon_pipelines.contracts import ProductCandidate, VideoTemplateRecord
from hackathon_pipelines.prototype_bridge import (
    LOCKED_REFERENCE_VEO_SYSTEM_PROMPT,
    MarketingVideoAnalysis,
    append_marketing_analysis_csv,
    build_fallback_veo_user_prompt,
    build_locked_reference_veo_prompt,
    build_single_concept_veo_user_prompt_request,
    build_veo_prompt_package,
    build_weighted_marketing_synthesis_prompt,
    load_marketing_analysis_csvs,
    parse_action_hook_music_sections,
    write_locked_veo_prompt_files,
    write_veo_prompt_package_files,
)


def test_parse_action_hook_music_sections() -> None:
    action, hook, music = parse_action_hook_music_sections(
        "ACTION: hand lifts can\nHOOK: neon glow stops the scroll\nMUSIC: synthwave pulse"
    )
    assert action == "hand lifts can"
    assert hook == "neon glow stops the scroll"
    assert music == "synthwave pulse"


def test_build_weighted_marketing_synthesis_prompt() -> None:
    prompt = build_weighted_marketing_synthesis_prompt(
        [
            MarketingVideoAnalysis(
                video_file="demo.mp4",
                action="spin reveal",
                hook="unexpected opening frame",
                music="upbeat lo-fi",
                views=120000,
                likes=5300,
            )
        ]
    )
    assert "VIEWS: 120,000 | LIKES: 5,300" in prompt
    assert "ACTION: spin reveal" in prompt


def test_append_and_load_marketing_analysis_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    append_marketing_analysis_csv(
        csv_path,
        MarketingVideoAnalysis(
            video_file="video_a.mp4",
            asset_id="asset123",
            timestamp="2026-04-04T12:00:00Z",
            action="show product",
            hook="hard cut",
            music="driving beat",
            views=5000,
            likes=200,
        ),
    )
    rows = load_marketing_analysis_csvs([csv_path])
    assert len(rows) == 1
    assert rows[0].video_file == "video_a.mp4"
    assert rows[0].asset_id == "asset123"


def test_build_locked_reference_veo_prompt() -> None:
    prompt = build_locked_reference_veo_prompt("Shoot a fast storefront reel with a strong hook.")
    assert "USER CREATIVE DIRECTION:" in prompt
    assert "Shoot a fast storefront reel with a strong hook." in prompt
    assert LOCKED_REFERENCE_VEO_SYSTEM_PROMPT.splitlines()[0] in prompt


def test_locked_reference_system_prompt_includes_asset_and_motion_rules() -> None:
    prompt = LOCKED_REFERENCE_VEO_SYSTEM_PROMPT.lower()
    assert "pixel-perfect exact replica" in prompt
    assert "no teleporting" in prompt
    assert "at most two distinct hero products" in prompt


def test_build_fallback_veo_user_prompt_is_concise_and_single_concept() -> None:
    user_prompt = build_fallback_veo_user_prompt(
        VideoTemplateRecord(
            template_id="tpl_1",
            structure_record_id="struct_1",
            veo_prompt_draft="Winning reel uses a tactile opener, warm rim light, and a smooth push-in.",
        ),
        ProductCandidate(
            product_id="prod_1",
            title="Glow Serum",
            source_url="https://example.com/product",
            notes="Hydrating serum for a creator-style beauty reel.",
        ),
        product_description="Hydrating serum with a glossy beauty-demo feel.",
        creative_brief="Base prompt from winning reel research: tactile opener and warm cinematic lighting.",
    )
    assert "Glow Serum" in user_prompt
    assert "8-second vertical" in user_prompt
    assert len(user_prompt.split()) <= 75


def test_build_single_concept_veo_user_prompt_request_uses_json_contract() -> None:
    request = build_single_concept_veo_user_prompt_request(
        VideoTemplateRecord(
            template_id="tpl_1",
            structure_record_id="struct_1",
            veo_prompt_draft="Creator lifts the product from a marble table and smiles into camera.",
        ),
        ProductCandidate(
            product_id="prod_1",
            title="Glow Serum",
            source_url="https://example.com/product",
        ),
        product_description="Hydrating serum for a bright creator-style beauty demo.",
        creative_brief="Use the winning hook and warm light from the source template.",
    )
    assert "Return ONLY valid JSON" in request
    assert '"user_prompt":"..."' in request
    assert "Glow Serum" in request
    assert "under 75 words" in request


def test_write_locked_veo_prompt_files(tmp_path: Path) -> None:
    system_path, user_path = write_locked_veo_prompt_files(
        output_dir=tmp_path / "veo",
        user_prompt="Make a strong opener and keep the product centered.",
    )
    assert system_path.exists()
    assert user_path.exists()
    assert (tmp_path / "veo" / "full_prompt.txt").exists()
    assert "Make a strong opener" in user_path.read_text(encoding="utf-8")


def test_write_veo_prompt_package_files_records_artifact_paths(tmp_path: Path) -> None:
    prompt_package = build_veo_prompt_package("Make a strong opener and keep the product centered.")
    written = write_veo_prompt_package_files(output_dir=tmp_path / "artifacts", prompt_package=prompt_package)
    assert written.artifact_dir == str(tmp_path / "artifacts")
    assert Path(written.system_prompt_path).exists()
    assert Path(written.user_prompt_path).exists()
    assert Path(written.full_prompt_path).exists()
