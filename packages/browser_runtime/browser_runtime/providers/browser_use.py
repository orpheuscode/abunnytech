"""
BrowserUseProvider — executes tasks via the browser-use agent loop.

browser-use: https://github.com/browser-use/browser-use
Install:  pip install browser-use playwright && playwright install chromium

Uses Gemini by default (`ChatGoogle`) when the model name starts with `gemini` or when
`BROWSER_USE_LLM=google`. Otherwise uses `ChatOpenAI` (set `OPENAI_API_KEY`).
Override with `BROWSER_USE_LLM=openai` or `BROWSER_USE_LLM=google`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from typing import Any

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


def _build_default_llm(model: str) -> Any:
    backend = os.getenv("BROWSER_USE_LLM", "").strip().lower()
    m = (model or "").lower()

    if backend == "openai" or (not backend and m.startswith(("gpt", "o1", "o3"))):
        from browser_use import ChatOpenAI

        return ChatOpenAI(model=model or "gpt-4o")

    if backend == "google" or m.startswith("gemini") or not backend:
        from browser_use import ChatGoogle

        gemini_model = model if m.startswith("gemini") else os.getenv("BROWSER_USE_GEMINI_MODEL", "gemini-2.5-flash")
        return ChatGoogle(model=gemini_model)

    from browser_use import ChatOpenAI

    return ChatOpenAI(model=model or "gpt-4o")


class BrowserUseProvider(BrowserProvider):
    """
    Wraps the browser-use Agent to execute open-ended browsing tasks.

    When browser-use is not installed, raises RuntimeError.
    """

    def __init__(
        self,
        llm_model: str = "gemini-2.5-flash",
        dry_run: bool = True,
        *,
        llm: Any | None = None,
    ) -> None:
        if not _BROWSER_USE_AVAILABLE:
            raise RuntimeError(
                "browser-use is not installed. "
                "Run: pip install 'browser-runtime[browser_use]' && playwright install chromium"
            )
        self._llm_model = llm_model
        self._dry_run = dry_run
        self._injected_llm = llm
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

        from browser_use import Agent

        self._audit.log_request("browser_use", "run_agent_task", task.task_id, False)
        llm = self._injected_llm or _build_default_llm(self._llm_model)
        full_task = task.description
        if task.url:
            full_task = f"Open {task.url} first. {full_task}"

        agent = Agent(
            task=full_task,
            llm=llm,
            max_actions_per_step=min(10, max(3, task.max_steps // 4 or 5)),
        )
        start = time.monotonic()
        try:
            history = await agent.run(max_steps=task.max_steps)
        except Exception as exc:
            self._audit.log(
                "browser_use.run_agent_task.error",
                {"task_id": task.task_id, "error": str(exc)},
            )
            return AgentResult(
                task_id=task.task_id,
                success=False,
                provider=ProviderType.BROWSER_USE,
                duration_seconds=time.monotonic() - start,
                output={"error": str(exc)},
                error=str(exc),
                dry_run=False,
            )

        duration = time.monotonic() - start
        final_text = history.final_result()
        output: dict[str, Any] = {"final_result": final_text}
        if isinstance(final_text, str) and final_text.strip().startswith("{"):
            try:
                parsed = json.loads(final_text)
                if isinstance(parsed, dict):
                    output.update(parsed)
            except json.JSONDecodeError:
                pass

        success_flag = history.is_successful()
        success = (not history.has_errors()) if success_flag is None else bool(success_flag)

        return AgentResult(
            task_id=task.task_id,
            success=success,
            provider=ProviderType.BROWSER_USE,
            duration_seconds=duration,
            steps_taken=len(history),
            output=output,
            dry_run=False,
        )

    async def bulk_extract(self, urls: list[str], schema: ExtractionSchema) -> list[ExtractionResult]:
        raise NotImplementedError("BrowserUseProvider.bulk_extract: see CodeAgentProvider for bulk extraction.")

    async def invoke_skill(self, request: SkillRequest) -> SkillResult:
        raise NotImplementedError("BrowserUseProvider.invoke_skill: use SkillAPIProvider instead.")

    async def call_platform_api(self, request: PlatformAPIRequest) -> PlatformAPIResponse:
        raise NotImplementedError("BrowserUseProvider.call_platform_api: use PlatformAPIProvider instead.")
