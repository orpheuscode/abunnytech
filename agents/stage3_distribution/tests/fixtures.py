"""
Shared test fixtures for Stage 3 tests.

All fixtures are synchronous factory functions that return fresh model instances.
Import what you need — no global state.
"""
from __future__ import annotations

from datetime import datetime

from ..contracts import (
    CommentStyle,
    ContentPackage,
    IdentityMatrix,
    Platform,
)


def make_identity(
    persona_name: str = "bunnygirl",
    niche: str = "fashion",
    target_platforms: list[Platform] | None = None,
) -> IdentityMatrix:
    return IdentityMatrix(
        identity_id="test-identity-001",
        persona_name=persona_name,
        display_name="Bunny 🐰",
        niche=niche,
        bio="Test persona",
        voice_tags=["playful", "warm"],
        hashtags=["#bunnygirl", "#test"],
        target_platforms=target_platforms or [Platform.TIKTOK, Platform.INSTAGRAM],
        comment_style=CommentStyle(
            tone="friendly",
            use_emojis=True,
            avg_reply_length=80,
            trigger_keywords=["link", "where", "buy", "how", "price"],
            dm_offer_template="Hey! DM me for the link 🐰",
            positive_reply_templates=["Thank you! 🥰", "You're so sweet! 💕"],
            question_reply_templates=["Great question! {answer} 🐰"],
            faq={"outfit": "DM me!"},
        ),
        ai_disclosure_footer="✨ AI-assisted | @{persona_name}",
    )


def make_package(
    content_type: str = "short_video",
    title: str = "5 pastel fits 🐰",
    caption: str = "POV: main character energy ✨",
    target_platforms: list[Platform] | None = None,
    priority: int = 2,
) -> ContentPackage:
    return ContentPackage(
        package_id="test-package-001",
        blueprint_id="test-blueprint-001",
        content_type=content_type,
        title=title,
        caption=caption,
        hashtags=["#bunnygirl", "#test"],
        media_path=None,
        media_url=None,
        target_platforms=target_platforms or [Platform.TIKTOK, Platform.INSTAGRAM],
        priority=priority,
        identity_id="test-identity-001",
        created_at=datetime(2026, 4, 4, 12, 0, 0),
    )
