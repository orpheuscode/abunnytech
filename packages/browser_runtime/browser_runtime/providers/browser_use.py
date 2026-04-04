"""
BrowserUseProvider — executes tasks via the browser-use agent loop.

browser-use: https://github.com/browser-use/browser-use
Install:  pip install browser-use playwright && playwright install chromium

The agent is given a natural-language description and autonomously
navigates, clicks, and fills forms to complete the task.

Status: STUB — wire up browser-use once credentials are available.
  TODO: import browser_use; instantiate Agent with correct LLM config.
"""
from __future__ import annotations

import importlib.util
import time

from ..audit import get_audit
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
from .base import BrowserProvider

_BROWSER_USE_AVAILABLE = importlib.util.find_spec("browser_use") is not None
if _BROWSER_USE_AVAILABLE:
    from browser_use import Agent as _BrowserUseAgent  # type: ignore[import]  # noqa: F401


class BrowserUseProvider(BrowserProvider):
    """
    Wraps the browser-use Agent to execute open-ended browsing tasks.

    When browser-use is not installed or credentials are missing,
    raises a clear RuntimeError rather than silently failing.
    """

    def __init__(
        self,
        llm_model: str = "gpt-4o",
        dry_run: bool = True,
    ) -> None:
        if not _BROWSER_USE_AVAILABLE:
            raise RuntimeError(
                "browser-use is not installed. "
                "Run: pip install 'browser-runtime[browser_use]' && playwright install chromium"
            )
        self._llm_model = llm_model
        self._dry_run = dry_run
        self._audit = get_audit()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.BROWSER_USE

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    async def run_agent_task(self, task: AgentTask) -> AgentResult:
        self._assert_not_killed()
        if task.dry_run or self._dry_run:
            self._audit.log("browser_use.run_agent_task.dry_run", {"task_id": task.task_id})
            return AgentResult(
                task_id=task.task_id,
                success=True,
                provider=ProviderType.BROWSER_USE,
                output={"dry_run": True, "description": task.description},
                dry_run=True,
            )

        time.monotonic()
        self._audit.log_request("browser_use", "run_agent_task", task.task_id, False)

        # TODO: wire up actual browser-use Agent
        # from langchain_openai import ChatOpenAI
        # agent = _BrowserUseAgent(
        #     task=task.description,
        #     llm=ChatOpenAI(model=self._llm_model),
        #     max_actions_per_step=task.max_steps,
        # )
        # history = await agent.run(max_steps=task.max_steps)
        # success = not history.has_errors()
        # output = {"final_result": history.final_result()}
        raise NotImplementedError(
            "BrowserUseProvider.run_agent_task: set up LLM credentials and uncomment the agent wiring above."
        )

    async def bulk_extract(self, urls: list[str], schema: ExtractionSchema) -> list[ExtractionResult]:
        # TODO: use browser-use's extraction loop or a dedicated CodeAgent pass
        raise NotImplementedError("BrowserUseProvider.bulk_extract: see CodeAgentProvider for bulk extraction.")

    async def invoke_skill(self, request: SkillRequest) -> SkillResult:
        raise NotImplementedError("BrowserUseProvider.invoke_skill: use SkillAPIProvider instead.")

    async def call_platform_api(self, request: PlatformAPIRequest) -> PlatformAPIResponse:
        raise NotImplementedError("BrowserUseProvider.call_platform_api: use PlatformAPIProvider instead.")
