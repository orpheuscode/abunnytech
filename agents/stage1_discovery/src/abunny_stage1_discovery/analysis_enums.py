from __future__ import annotations

from enum import StrEnum


class HookLabel(StrEnum):
    PATTERN_INTERRUPT = "pattern_interrupt"
    CURIOSITY_GAP = "curiosity_gap"
    STORY = "story"
    TUTORIAL = "tutorial"
    LISTICLE = "listicle"
    UNKNOWN = "unknown"


class CtaKind(StrEnum):
    NONE = "none"
    SOFT = "soft"
    HARD = "hard"
    LINK_IN_BIO = "link_in_bio"


class ProductIntegration(StrEnum):
    NONE = "none"
    SUBTLE = "subtle"
    PROMINENT = "prominent"
    HEAVY_BRANDED = "heavy_branded"
