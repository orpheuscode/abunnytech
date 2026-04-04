"""Thin wrapper so pipelines depend on a port, not raw `BrowserProvider`."""

from __future__ import annotations

from browser_runtime.providers.base import BrowserProvider
from browser_runtime.types import AgentResult, AgentTask

from hackathon_pipelines.ports import BrowserAutomationPort


class BrowserProviderFacade(BrowserAutomationPort):
    def __init__(self, provider: BrowserProvider) -> None:
        self._provider = provider

    async def run_task(self, task: AgentTask) -> AgentResult:
        return await self._provider.run_agent_task(task)
