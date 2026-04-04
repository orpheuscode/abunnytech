"""Provider registry and factory."""
from __future__ import annotations

from .base import BrowserProvider
from .browser_use import BrowserUseProvider
from .code_agent import CodeAgentProvider
from .mock import MockProvider
from .platform_api import PlatformAPIProvider
from .skill_api import SkillAPIProvider


def get_provider(provider_name: str | None = None, dry_run: bool = True) -> BrowserProvider:
    """
    Return a provider instance by name.

    Falls back to MockProvider if provider_name is None or "mock".
    Reads BROWSER_PROVIDER env var if provider_name is not supplied.
    """
    import os
    name = provider_name or os.getenv("BROWSER_PROVIDER", "mock")
    match name.lower():
        case "mock":
            return MockProvider(dry_run=dry_run)
        case "browser_use":
            return BrowserUseProvider(dry_run=dry_run)
        case "code_agent":
            return CodeAgentProvider(dry_run=dry_run)
        case "skill_api":
            return SkillAPIProvider(dry_run=dry_run)
        case "platform_api":
            return PlatformAPIProvider(dry_run=dry_run)
        case _:
            choices = "mock, browser_use, code_agent, skill_api, platform_api"
            raise ValueError(f"Unknown provider: {name!r}. Choices: {choices}")


__all__ = [
    "BrowserProvider",
    "BrowserUseProvider",
    "CodeAgentProvider",
    "MockProvider",
    "PlatformAPIProvider",
    "SkillAPIProvider",
    "get_provider",
]
