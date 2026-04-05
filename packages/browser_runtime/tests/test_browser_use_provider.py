from __future__ import annotations

import sys
import types

import pytest

from browser_runtime.providers import browser_use as browser_use_module
from browser_runtime.types import AgentTask, ProviderType


def test_browser_use_browser_config_to_kwargs() -> None:
    config = browser_use_module.BrowserUseBrowserConfig(
        cdp_url="http://localhost:9222",
        use_cloud=True,
        cloud_profile_id="profile-123",
        extra_kwargs={"downloads_path": "downloads"},
    )
    assert config.to_browser_kwargs() == {
        "cdp_url": "http://localhost:9222",
        "use_cloud": True,
        "cloud_profile_id": "profile-123",
        "downloads_path": "downloads",
    }


@pytest.mark.asyncio
async def test_run_agent_task_uses_chatbrowseruse_and_browser_config(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChatBrowserUse:
        pass

    class FakeBrowser:
        def __init__(self, **kwargs):
            captured["browser_kwargs"] = kwargs

    class FakeHistory:
        structured_output = None

        def final_result(self) -> str:
            return '{"ok": true}'

        def urls(self) -> list[str]:
            return ["https://www.instagram.com/reel/demo123/"]

        def action_names(self) -> list[str]:
            return ["open_tab", "scroll", "extract"]

        def errors(self) -> list[str | None]:
            return [None, None, None]

        def action_history(self) -> list[dict[str, object]]:
            return [{"name": "open_tab"}, {"name": "scroll"}, {"name": "extract"}]

        def number_of_steps(self) -> int:
            return 3

        def is_successful(self) -> bool:
            return True

        def has_errors(self) -> bool:
            return False

        def __len__(self) -> int:
            return 3

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs

        async def run(self, max_steps: int):
            captured["max_steps"] = max_steps
            return FakeHistory()

    fake_browser_use = types.ModuleType("browser_use")
    fake_browser_use.ChatBrowserUse = FakeChatBrowserUse
    fake_browser_use.ChatOpenAI = lambda model=None: ("openai", model)
    fake_browser_use.ChatGoogle = lambda model=None: ("google", model)
    fake_browser_use.ChatAnthropic = lambda model=None: ("anthropic", model)
    fake_browser_use.Browser = FakeBrowser
    fake_browser_use.Agent = FakeAgent

    monkeypatch.setattr(browser_use_module, "_BROWSER_USE_AVAILABLE", True)
    monkeypatch.setitem(sys.modules, "browser_use", fake_browser_use)

    provider = browser_use_module.BrowserUseProvider(
        dry_run=False,
        browser_config=browser_use_module.BrowserUseBrowserConfig(
            cdp_url="http://localhost:9222",
            use_cloud=True,
        ),
    )
    result = await provider.run_agent_task(AgentTask(description="Collect reels", max_steps=7))

    assert result.success is True
    assert result.provider == ProviderType.BROWSER_USE
    assert result.output["trace"]["urls"] == ["https://www.instagram.com/reel/demo123/"]
    assert result.output["trace"]["action_names"] == ["open_tab", "scroll", "extract"]
    assert result.output["trace"]["number_of_steps"] == 3
    assert captured["browser_kwargs"] == {"cdp_url": "http://localhost:9222", "use_cloud": True}
    agent_kwargs = captured["agent_kwargs"]
    assert isinstance(agent_kwargs["llm"], FakeChatBrowserUse)
    assert isinstance(agent_kwargs["browser"], FakeBrowser)
    assert captured["max_steps"] == 7


@pytest.mark.asyncio
async def test_run_agent_task_forwards_browser_use_task_metadata(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChatBrowserUse:
        pass

    class FakeHistory:
        structured_output = None

        def final_result(self) -> str:
            return '{"ok": true}'

        def is_successful(self) -> bool:
            return True

        def has_errors(self) -> bool:
            return False

        def __len__(self) -> int:
            return 1

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs

        async def run(self, max_steps: int):
            captured["max_steps"] = max_steps
            return FakeHistory()

    fake_browser_use = types.ModuleType("browser_use")
    fake_browser_use.ChatBrowserUse = FakeChatBrowserUse
    fake_browser_use.ChatOpenAI = lambda model=None: ("openai", model)
    fake_browser_use.ChatGoogle = lambda model=None: ("google", model)
    fake_browser_use.ChatAnthropic = lambda model=None: ("anthropic", model)
    fake_browser_use.Agent = FakeAgent

    monkeypatch.setattr(browser_use_module, "_BROWSER_USE_AVAILABLE", True)
    monkeypatch.setitem(sys.modules, "browser_use", fake_browser_use)

    provider = browser_use_module.BrowserUseProvider(dry_run=False)
    task = AgentTask(
        description="Scroll the reels feed repeatedly",
        max_steps=9,
        metadata={
            "browser_use": {
                "use_vision": True,
                "vision_detail_level": "high",
                "step_timeout": 180,
                "llm_timeout": 120,
                "max_actions_per_step": 5,
                "extend_system_message": "Keep scrolling before done.",
            }
        },
    )

    result = await provider.run_agent_task(task)

    assert result.success is True
    agent_kwargs = captured["agent_kwargs"]
    assert isinstance(agent_kwargs["llm"], FakeChatBrowserUse)
    assert agent_kwargs["use_vision"] is True
    assert agent_kwargs["vision_detail_level"] == "high"
    assert agent_kwargs["step_timeout"] == 180
    assert agent_kwargs["llm_timeout"] == 120
    assert agent_kwargs["max_actions_per_step"] == 5
    assert agent_kwargs["extend_system_message"] == "Keep scrolling before done."
