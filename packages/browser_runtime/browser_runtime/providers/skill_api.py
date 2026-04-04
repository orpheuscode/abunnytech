"""
SkillAPIProvider — invokes pre-built Skill API macros via HTTP.

Skills are named, parameterised browser macros hosted by an external
Skill API server.  This provider translates SkillRequest objects into
HTTP calls and maps the JSON response back to SkillResult.

Status: STUB — set BROWSER_SKILL_API_BASE_URL to activate.
"""
from __future__ import annotations

import os
import time

import httpx

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


class SkillAPIProvider(BrowserProvider):
    """
    Routes SkillRequest → Skill API HTTP endpoint → SkillResult.

    Required env var: BROWSER_SKILL_API_BASE_URL
    Optional:         BROWSER_SKILL_API_KEY
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._base_url = os.getenv("BROWSER_SKILL_API_BASE_URL", "")
        self._api_key = os.getenv("BROWSER_SKILL_API_KEY", "")
        self._audit = get_audit()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.SKILL_API

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    async def run_agent_task(self, task: AgentTask) -> AgentResult:
        raise NotImplementedError("SkillAPIProvider: use BrowserUseProvider for agent tasks.")

    async def bulk_extract(self, urls: list[str], schema: ExtractionSchema) -> list[ExtractionResult]:
        raise NotImplementedError("SkillAPIProvider: use CodeAgentProvider for bulk extraction.")

    async def invoke_skill(self, request: SkillRequest) -> SkillResult:
        self._assert_not_killed()
        t0 = time.monotonic()
        self._audit.log_request("skill_api", "invoke_skill", request.request_id, request.dry_run)

        if request.dry_run or self._dry_run:
            return SkillResult(
                request_id=request.request_id,
                skill_name=request.skill_name,
                success=True,
                result={"dry_run": True},
            )

        if not self._base_url:
            raise RuntimeError(
                "BROWSER_SKILL_API_BASE_URL is not set. "
                "Set it or use dry_run=True / MockProvider."
            )

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(base_url=self._base_url, timeout=request.timeout_seconds) as client:
            resp = await client.post(
                f"/skills/{request.skill_name}/run",
                json=request.params,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        result = SkillResult(
            request_id=request.request_id,
            skill_name=request.skill_name,
            success=True,
            result=data,
            duration_seconds=round(time.monotonic() - t0, 3),
        )
        self._audit.log_result("skill_api", "invoke_skill", request.request_id, True, False)
        return result

    async def call_platform_api(self, request: PlatformAPIRequest) -> PlatformAPIResponse:
        raise NotImplementedError("SkillAPIProvider: use PlatformAPIProvider for raw platform API calls.")
