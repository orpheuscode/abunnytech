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
import inspect
import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

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
    isolate_local_browser_profile: bool | None = None
    executable_path: str | None = None
    user_data_dir: str | None = None
    profile_directory: str | None = None
    downloads_path: str | None = None
    cloud_profile_id: str | None = None
    cloud_proxy_country_code: str | None = None
    cloud_timeout: int | None = Field(default=None, ge=1)
    minimum_wait_page_load_time: float | None = Field(default=None, ge=0.0)
    wait_for_network_idle_page_load_time: float | None = Field(default=None, ge=0.0)
    wait_between_actions: float | None = Field(default=None, ge=0.0)
    highlight_elements: bool | None = None
    paint_order_filtering: bool | None = None
    extra_kwargs: dict[str, Any] = Field(default_factory=dict)

    def to_browser_kwargs(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True, exclude={"extra_kwargs", "isolate_local_browser_profile"})
        data.update(self.extra_kwargs)
        return data


class BrowserUseAgentConfig(BaseModel):
    """Typed subset of Browser Use agent settings passed through task metadata."""

    model_config = ConfigDict(extra="forbid")

    use_vision: bool | Literal["auto"] | None = None
    vision_detail_level: Literal["low", "high", "auto"] | None = None
    initial_actions: list[dict[str, Any]] | None = None
    max_actions_per_step: int | None = Field(default=None, ge=1, le=20)
    step_timeout: int | None = Field(default=None, ge=1)
    llm_timeout: int | None = Field(default=None, ge=1)
    extend_system_message: str | None = None
    flash_mode: bool | None = None
    use_thinking: bool | None = None
    directly_open_url: bool | None = None

    def to_agent_kwargs(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


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


def _coerce_jsonable(value: Any) -> Any:
    """Convert Browser Use history values into JSON-safe payloads."""

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _coerce_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _call_history_method(history: Any, method_name: str) -> Any | None:
    """Safely call an optional Browser Use history helper method."""

    method = getattr(history, method_name, None)
    if not isinstance(method, Callable):
        return None
    try:
        return method()
    except Exception:
        return None


def _history_trace(history: Any) -> dict[str, Any]:
    """Build a compact trace of Browser Use execution for logs and UI."""

    trace = {
        "urls": _call_history_method(history, "urls"),
        "action_names": _call_history_method(history, "action_names"),
        "errors": _call_history_method(history, "errors"),
        "action_history": _call_history_method(history, "action_history"),
        "action_results": _call_history_method(history, "action_results"),
        "model_actions": _call_history_method(history, "model_actions"),
        "model_outputs": _call_history_method(history, "model_outputs"),
        "screenshots": _call_history_method(history, "screenshot_paths"),
    }
    cleaned = {key: _coerce_jsonable(value) for key, value in trace.items() if value not in (None, [], {}, ())}
    cleaned["is_done"] = _call_history_method(history, "is_done")
    cleaned["number_of_steps"] = _call_history_method(history, "number_of_steps") or len(history)
    cleaned["total_duration_seconds"] = _call_history_method(history, "total_duration_seconds")
    return {key: value for key, value in cleaned.items() if value is not None}


def _agent_config_from_task(task: AgentTask) -> BrowserUseAgentConfig:
    raw = task.metadata.get("browser_use")
    if isinstance(raw, dict):
        return BrowserUseAgentConfig.model_validate(raw)

    legacy: dict[str, Any] = {}
    for field_name in BrowserUseAgentConfig.model_fields:
        legacy_key = f"browser_use_{field_name}"
        if legacy_key in task.metadata:
            legacy[field_name] = task.metadata[legacy_key]
    if legacy:
        return BrowserUseAgentConfig.model_validate(legacy)
    return BrowserUseAgentConfig()


def _agent_passthrough_kwargs_from_task(task: AgentTask) -> dict[str, Any]:
    """Allow task-local Browser Use objects such as custom tools."""

    extras: dict[str, Any] = {}
    tools = task.metadata.get("browser_use_tools")
    if tools is not None:
        extras["tools"] = tools

    output_model_schema = task.metadata.get("browser_use_output_model_schema")
    if output_model_schema is not None:
        extras["output_model_schema"] = output_model_schema

    raw_agent_kwargs = task.metadata.get("browser_use_agent_kwargs")
    if isinstance(raw_agent_kwargs, dict):
        extras.update(raw_agent_kwargs)

    return extras


def _browser_config_from_task(task: AgentTask) -> BrowserUseBrowserConfig | None:
    raw = task.metadata.get("browser_use_browser")
    if isinstance(raw, BrowserUseBrowserConfig):
        return raw
    if isinstance(raw, dict):
        return BrowserUseBrowserConfig.model_validate(raw)

    legacy: dict[str, Any] = {}
    for field_name in BrowserUseBrowserConfig.model_fields:
        legacy_key = f"browser_use_browser_{field_name}"
        if legacy_key in task.metadata:
            legacy[field_name] = task.metadata[legacy_key]
    if legacy:
        return BrowserUseBrowserConfig.model_validate(legacy)
    return None


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

    def _build_browser(self, task: AgentTask) -> tuple[Any | None, Path | None]:
        task_browser_config = _browser_config_from_task(task)
        if self._browser_config is None and task_browser_config is None:
            return None, None
        if self._browser_config is None:
            resolved_config = task_browser_config.model_copy(deep=True)
        elif task_browser_config is None:
            resolved_config = self._browser_config.model_copy(deep=True)
        else:
            override_payload = task_browser_config.model_dump(
                exclude_unset=True,
                exclude={"extra_kwargs"},
            )
            resolved_config = self._browser_config.model_copy(
                update={
                    **override_payload,
                    "extra_kwargs": {
                        **self._browser_config.extra_kwargs,
                        **task_browser_config.extra_kwargs,
                    },
                },
                deep=True,
            )
        cleanup_dir: Path | None = None
        if (
            resolved_config.isolate_local_browser_profile
            and resolved_config.cdp_url is None
            and resolved_config.executable_path
            and resolved_config.user_data_dir
            and resolved_config.profile_directory
        ):
            source_root = Path(resolved_config.user_data_dir)
            profile_source = source_root / resolved_config.profile_directory
            if not profile_source.exists():
                msg = f"Chrome profile does not exist for isolated Browser Use task: {profile_source}"
                raise FileNotFoundError(msg)
            cleanup_dir = Path(tempfile.mkdtemp(prefix=f"browser-use-{task.task_id[:8]}-"))
            for file_name in ("Local State", "First Run"):
                source_file = source_root / file_name
                if source_file.exists():
                    shutil.copy2(source_file, cleanup_dir / file_name)
            shutil.copytree(profile_source, cleanup_dir / resolved_config.profile_directory)
            resolved_config = resolved_config.model_copy(
                update={
                    "user_data_dir": str(cleanup_dir),
                    # Isolated task profiles should not stay alive after the task finishes.
                    "keep_alive": False,
                }
            )

        browser_kwargs = resolved_config.to_browser_kwargs()
        if not browser_kwargs:
            return None, cleanup_dir
        from browser_use import Browser

        return Browser(**browser_kwargs), cleanup_dir

    async def _close_browser(self, browser: Any | None, *, cleanup_dir: Path | None) -> None:
        if browser is not None:
            closer = getattr(browser, "close", None)
            if callable(closer):
                try:
                    maybe_awaitable = closer()
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                except Exception:
                    pass
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)

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
        browser = None
        cleanup_dir: Path | None = None
        agent_config = _agent_config_from_task(task)
        full_task = task.description
        if task.url:
            full_task = f"Open {task.url} first. {full_task}"

        agent_kwargs: dict[str, Any] = dict(
            task=full_task,
            llm=llm,
            max_actions_per_step=agent_config.max_actions_per_step or min(10, max(3, task.max_steps // 4 or 5)),
        )
        agent_kwargs.update(agent_config.to_agent_kwargs())
        agent_kwargs.update(_agent_passthrough_kwargs_from_task(task))
        start = time.monotonic()
        try:
            browser, cleanup_dir = self._build_browser(task)
            if browser is not None:
                agent_kwargs["browser"] = browser
            agent = Agent(**agent_kwargs)
            history = await agent.run(max_steps=task.max_steps)
        except Exception as exc:
            self._audit.log(
                "browser_use.run_agent_task.error",
                {"task_id": task.task_id, "error": str(exc)},
            )
            self._audit.log_result("browser_use", "run_agent_task", task.task_id, False, False, {"error": str(exc)})
            return AgentResult(
                task_id=task.task_id,
                success=False,
                provider=ProviderType.BROWSER_USE,
                duration_seconds=time.monotonic() - start,
                output={"error": str(exc)},
                error=str(exc),
                dry_run=False,
            )
        finally:
            await self._close_browser(browser, cleanup_dir=cleanup_dir)

        duration = time.monotonic() - start
        final_text = history.final_result()
        output: dict[str, Any] = {"final_result": final_text}
        trace = _history_trace(history)
        output["trace"] = trace
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
        self._audit.log(
            "browser_use.run_agent_task.history",
            {"task_id": task.task_id, "success": success, "trace": trace},
            level="INFO" if success else "ERROR",
        )
        self._audit.log_result(
            "browser_use",
            "run_agent_task",
            task.task_id,
            success,
            False,
            {
                "duration_seconds": duration,
                "steps_taken": len(history),
                "visited_urls": len(trace.get("urls", [])) if isinstance(trace.get("urls"), list) else None,
                "actions": len(trace.get("action_names", []))
                if isinstance(trace.get("action_names"), list)
                else None,
            },
        )

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
