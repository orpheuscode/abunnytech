"""
browser_runtime — shared browser/runtime abstraction layer.

All browser-facing stages import from here.

Quick start (mock, zero credentials):
    from browser_runtime import get_provider, get_adapter
    from browser_runtime.types import PostContentRequest, Platform

    provider = get_provider("mock", dry_run=True)
    adapter = get_adapter("tiktok", provider)
    result = await adapter.post_content(
        PostContentRequest(
            platform=Platform.TIKTOK,
            caption="AI-generated content | made with #AI",
            dry_run=True,
        )
    )
    print(result.post_id)   # DRY-RUN-xxxxxxxx

For live posting:
    provider = get_provider("browser_use", dry_run=False)
    # Set TIKTOK_ACCESS_TOKEN, etc. in .env
"""

__version__ = "0.1.0"

from .adapters import get_adapter
from .providers import get_provider
from .session import InMemorySession, KillSwitchTriggered, SessionManager

__all__ = [
    "__version__",
    "get_provider",
    "get_adapter",
    "InMemorySession",
    "KillSwitchTriggered",
    "SessionManager",
]
