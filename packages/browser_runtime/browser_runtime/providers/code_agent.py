"""
CodeAgentProvider — bulk structured extraction via a code-writing agent.

The agent writes and executes Python/JS snippets to scrape structured data
from multiple URLs in a single pass.  Suitable for trend discovery, analytics
exports, and competitor analysis (Stage 1 and Stage 4 workloads).

Status: STUB — implement once agent framework choice is confirmed.
  TODO: integrate smolagents CodeAgent or equivalent.
"""
from __future__ import annotations

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


class CodeAgentProvider(BrowserProvider):
    """
    Executes structured extraction tasks via a code-writing agent.

    Dry-run mode returns empty ExtractionResult stubs with dry_run markers.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._audit = get_audit()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.CODE_AGENT

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    async def run_agent_task(self, task: AgentTask) -> AgentResult:
        # CodeAgent is specialised for extraction; delegate general tasks to BrowserUseProvider
        raise NotImplementedError("CodeAgentProvider.run_agent_task: use BrowserUseProvider for general tasks.")

    async def bulk_extract(self, urls: list[str], schema: ExtractionSchema) -> list[ExtractionResult]:
        self._assert_not_killed()
        if self._dry_run:
            self._audit.log("code_agent.bulk_extract.dry_run", {"url_count": len(urls)})
            return [
                ExtractionResult(
                    url=url,
                    success=True,
                    data={"dry_run": True, **{field: None for field in schema.fields}},
                )
                for url in urls
            ]

        # TODO: implement code agent extraction
        # from smolagents import CodeAgent, HfApiModel
        # agent = CodeAgent(tools=[...], model=HfApiModel())
        # results = []
        # for url in urls:
        #     code_output = agent.run(f"Extract {schema.fields} from {url}")
        #     results.append(ExtractionResult(url=url, success=True, data=code_output))
        # return results
        raise NotImplementedError(
            "CodeAgentProvider.bulk_extract: uncomment and configure smolagents above."
        )

    async def invoke_skill(self, request: SkillRequest) -> SkillResult:
        raise NotImplementedError("CodeAgentProvider.invoke_skill: use SkillAPIProvider.")

    async def call_platform_api(self, request: PlatformAPIRequest) -> PlatformAPIResponse:
        raise NotImplementedError("CodeAgentProvider.call_platform_api: use PlatformAPIProvider.")
