"""Adapter registry and factory."""
from __future__ import annotations

from ..providers.base import BrowserProvider
from ..types import Platform
from .analytics import AnalyticsAdapter
from .base import PlatformAdapter
from .instagram import InstagramAdapter
from .shopify import ShopifyAdapter
from .tiktok import TikTokAdapter


def get_adapter(platform: str | Platform, provider: BrowserProvider) -> PlatformAdapter:
    """
    Return a PlatformAdapter for the given platform name.

    Usage:
        provider = get_provider("mock", dry_run=True)
        adapter = get_adapter("tiktok", provider)
        result = await adapter.post_content(request)
    """
    p = Platform(platform) if isinstance(platform, str) else platform
    match p:
        case Platform.TIKTOK:
            return TikTokAdapter(provider)
        case Platform.INSTAGRAM:
            return InstagramAdapter(provider)
        case Platform.SHOPIFY:
            return ShopifyAdapter(provider)
        case Platform.ANALYTICS:
            return AnalyticsAdapter(provider)
        case _:
            raise ValueError(f"No adapter for platform: {platform!r}")


__all__ = [
    "PlatformAdapter",
    "TikTokAdapter",
    "InstagramAdapter",
    "ShopifyAdapter",
    "AnalyticsAdapter",
    "get_adapter",
]
