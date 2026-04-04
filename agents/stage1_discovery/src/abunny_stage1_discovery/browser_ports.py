"""Browser/runtime-facing ports.

These Protocols mirror what a real `packages.browser_runtime` implementation should
expose; Stage 1 depends only on this surface (no Playwright/network internals here).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from abunny_stage1_discovery.models import (
    AccountMetadata,
    DiscoveryPlan,
    MediaDownloadJob,
    RawShortCandidate,
)


@runtime_checkable
class ShortFormDiscoveryPort(Protocol):
    def discover_short_form(self, plan: DiscoveryPlan) -> list[RawShortCandidate]:
        """Return candidate shorts matching the discovery plan (URLs + light metadata)."""
        ...


@runtime_checkable
class AccountMetadataPort(Protocol):
    def extract_account_metadata(self, handle: str, platform: str) -> AccountMetadata | None:
        """Fetch public profile fields for a creator handle."""
        ...


@runtime_checkable
class MediaDownloadJobPlannerPort(Protocol):
    def plan_media_downloads(self, candidates: list[RawShortCandidate]) -> list[MediaDownloadJob]:
        """Produce prioritized download jobs for analysis (video/audio/thumb)."""
        ...
