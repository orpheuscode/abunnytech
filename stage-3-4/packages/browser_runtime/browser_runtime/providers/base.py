"""
BrowserProvider abstract base class.

A provider knows HOW to execute a task (agent loop, code extraction, API call).
It is platform-agnostic; platform specifics live in adapters/.

Dependency graph:
    Stage code → PlatformAdapter → BrowserProvider → external service
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import (
    AgentResult,
    AgentTask,
    ExtractionResult,
    ExtractionSchema,
    PlatformAPIRequest,
    PlatformAPIResponse,
    ProviderType,
    SkillRequest,
    SkillResult,
)


class BrowserProvider(ABC):
    """
    Abstract interface for all browser/runtime execution backends.

    Implementations:
        MockProvider        — in-memory, no credentials needed
        BrowserUseProvider  — uses browser-use agent loop
        CodeAgentProvider   — bulk extraction via CodeAgent
        SkillAPIProvider    — calls Skill API endpoints
        PlatformAPIProvider — routes through official platform REST APIs
    """

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType: ...

    @property
    @abstractmethod
    def dry_run(self) -> bool: ...

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    @abstractmethod
    async def run_agent_task(self, task: AgentTask) -> AgentResult:
        """
        Run an open-ended agent task (browse, click, fill forms, etc.).
        The agent interprets `task.description` and acts autonomously up to
        `task.max_steps` steps.
        """

    @abstractmethod
    async def bulk_extract(
        self,
        urls: list[str],
        schema: ExtractionSchema,
    ) -> list[ExtractionResult]:
        """
        Extract structured data from multiple URLs in one pass.
        Suitable for scraping trend data, analytics exports, etc.
        """

    @abstractmethod
    async def invoke_skill(self, request: SkillRequest) -> SkillResult:
        """
        Call a named Skill API endpoint.
        Skills are pre-built, parameterised browser macros.
        """

    @abstractmethod
    async def call_platform_api(self, request: PlatformAPIRequest) -> PlatformAPIResponse:
        """
        Route a call through an official platform REST/GraphQL API.
        Falls back to this when browser automation is not needed or preferred.
        """

    # ------------------------------------------------------------------
    # Helpers available to all subclasses
    # ------------------------------------------------------------------

    def _assert_not_killed(self, platform: str | None = None) -> None:
        from ..config import get_settings
        from ..session import KillSwitchTriggered
        settings = get_settings()
        if settings.global_kill_switch.enabled:
            raise KillSwitchTriggered(settings.global_kill_switch.reason)
        if platform:
            pc = settings.platform_config(platform)
            if pc.kill_switch.enabled:
                raise KillSwitchTriggered(pc.kill_switch.reason)
