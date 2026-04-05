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
    assert captured["browser_kwargs"] == {"cdp_url": "http://localhost:9222", "use_cloud": True}
    agent_kwargs = captured["agent_kwargs"]
    assert isinstance(agent_kwargs["llm"], FakeChatBrowserUse)
    assert isinstance(agent_kwargs["browser"], FakeBrowser)
    assert captured["max_steps"] == 7
