from __future__ import annotations

from pathlib import Path

from hackathon_pipelines.prototype_bridge import (
    LOCKED_REFERENCE_VEO_SYSTEM_PROMPT,
    MarketingVideoAnalysis,
    append_marketing_analysis_csv,
    build_locked_reference_veo_prompt,
    build_weighted_marketing_synthesis_prompt,
    load_marketing_analysis_csvs,
    parse_action_hook_music_sections,
    write_locked_veo_prompt_files,
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


def test_write_locked_veo_prompt_files(tmp_path: Path) -> None:
    system_path, user_path = write_locked_veo_prompt_files(
        output_dir=tmp_path / "veo",
        user_prompt="Make a strong opener and keep the product centered.",
    )
    assert system_path.exists()
    assert user_path.exists()
    assert "Make a strong opener" in user_path.read_text(encoding="utf-8")
