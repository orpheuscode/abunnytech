"""
BrowserUseProvider — executes tasks via the browser-use agent loop.

browser-use: https://github.com/browser-use/browser-use
Install:  uv pip install "browser-runtime[browser_use]" && playwright install chromium

Defaults to `ChatBrowserUse`, which is the recommended Browser Use model for browser
automation tasks. Alternative backends can still be selected by model prefix or by
setting `BROWSER_USE_LLM` to `google`, `openai`, or `anthropic`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


class BrowserUseBrowserConfig(BaseModel):
    """Typed Browser configuration forwarded to `browser_use.Browser` when provided."""

    model_config = ConfigDict(extra="forbid")

    cdp_url: str | None = None
    use_cloud: bool | None = None
    headless: bool | None = None
    keep_alive: bool | None = None
    executable_path: str | None = None
    user_data_dir: str | None = None
    profile_directory: str | None = None
    downloads_path: str | None = None
    cloud_profile_id: str | None = None
    cloud_proxy_country_code: str | None = None
    cloud_timeout: int | None = Field(default=None, ge=1)
    extra_kwargs: dict[str, Any] = Field(default_factory=dict)

    def to_browser_kwargs(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True, exclude={"extra_kwargs"})
        data.update(self.extra_kwargs)
        return data


def _build_default_llm(model: str) -> Any:
    backend = os.getenv("BROWSER_USE_LLM", "").strip().lower()
    raw_model = (model or "").strip()
    m = raw_model.lower()

    if backend in {"browser_use", "chatbrowseruse"} or (not backend and (not raw_model or m == "chatbrowseruse")):
        from browser_use import ChatBrowserUse

        return ChatBrowserUse()

    if backend == "openai" or (not backend and m.startswith(("gpt", "o1", "o3"))):
        from browser_use import ChatOpenAI

        return ChatOpenAI(model=raw_model or "gpt-4o")

    if backend == "anthropic" or (not backend and m.startswith("claude")):
        from browser_use import ChatAnthropic

        return ChatAnthropic(model=raw_model or "claude-sonnet-4-0")

    if backend == "google" or (not backend and m.startswith("gemini")):
        from browser_use import ChatGoogle

        gemini_model = (
            raw_model if m.startswith("gemini") else os.getenv("BROWSER_USE_GEMINI_MODEL", "gemini-2.5-flash")
        )
        return ChatGoogle(model=gemini_model)

    if raw_model:
        from browser_use import ChatOpenAI

        return ChatOpenAI(model=raw_model)

    from browser_use import ChatBrowserUse

    return ChatBrowserUse()


class BrowserUseProvider(BrowserProvider):
    """
    Wraps the browser-use Agent to execute open-ended browsing tasks.

    When browser-use is not installed, raises RuntimeError.
    """

    def __init__(
        self,
        llm_model: str = "ChatBrowserUse",
        dry_run: bool = True,
        *,
        llm: Any | None = None,
        browser_config: BrowserUseBrowserConfig | None = None,
    ) -> None:
        if not _BROWSER_USE_AVAILABLE:
            raise RuntimeError(
                "browser-use is not installed. "
                'Run: uv pip install "browser-runtime[browser_use]" && playwright install chromium'
            )
        self._llm_model = llm_model
        self._dry_run = dry_run
        self._injected_llm = llm
        self._browser_config = browser_config
        self._audit = get_audit()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.BROWSER_USE

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def _build_browser(self) -> Any | None:
        if self._browser_config is None:
            return None
        browser_kwargs = self._browser_config.to_browser_kwargs()
        if not browser_kwargs:
            return None
        from browser_use import Browser

        return Browser(**browser_kwargs)

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
        browser = self._build_browser()
        full_task = task.description
        if task.url:
            full_task = f"Open {task.url} first. {full_task}"

        agent_kwargs: dict[str, Any] = dict(
            task=full_task,
            llm=llm,
            max_actions_per_step=min(10, max(3, task.max_steps // 4 or 5)),
        )
        if browser is not None:
            agent_kwargs["browser"] = browser
        agent = Agent(**agent_kwargs)
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
        structured_output = getattr(history, "structured_output", None)
        if structured_output is not None:
            if hasattr(structured_output, "model_dump"):
                output["structured_output"] = structured_output.model_dump(mode="json")
            else:
                output["structured_output"] = structured_output
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
