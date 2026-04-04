"""Shared enumerations for handoff contracts (JSON-serializable string enums)."""

from __future__ import annotations

from enum import StrEnum


class PlatformTarget(StrEnum):
    """Platforms the identity matrix optimizes for."""

    TIKTOK = "tiktok"
    SHORTS = "shorts"
    INSTAGRAM_REELS = "instagram_reels"
    YOUTUBE_SHORTS = "youtube_shorts"


class DistributionPlatform(StrEnum):
    """Where a content package was or will be posted."""

    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
    INSTAGRAM = "instagram"
    MOCK = "mock"


class DistributionStatus(StrEnum):
    """Lifecycle of a distribution attempt."""

    PENDING = "pending"
    POSTED = "posted"
    FAILED = "failed"
    REMOVED = "removed"


class TrainingMaterialKind(StrEnum):
    """Kind of file referenced in a training manifest."""

    IMAGE = "image"
    TRANSCRIPT = "transcript"
    STYLE_REF = "style_ref"
    DOCUMENT = "document"
    OTHER = "other"


class DirectiveTargetStage(StrEnum):
    """Pipeline stage that may consume an optimization directive."""

    STAGE1 = "stage1"
    STAGE2 = "stage2"
    STAGE3 = "stage3"


class RedoReasonCode(StrEnum):
    """Common redo classifications (free-text reason still allowed on item)."""

    POLICY = "policy"
    QUALITY = "quality"
    BRAND = "brand"
    TECHNICAL = "technical"
    OTHER = "other"


class ProductAvailability(StrEnum):
    """High-level availability for catalog display."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"
