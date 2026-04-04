"""
MockProvider — fully in-memory, zero credentials required.

Suitable for:
  - unit and integration tests
  - offline demos / CI
  - dry-run mode in production (when dry_run=True is passed through)

Behaviour:
  - All operations succeed and return realistic-looking fixture data.
  - Any request with dry_run=True returns a DRY-RUN-prefixed post_id / message_id.
  - Call history is stored in self.calls for assertion in tests.
  - Supports optional failure injection via MockProvider.inject_failure(operation, exc).
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from ..audit import get_audit
from ..types import (
    AgentResult,
    AgentTask,
    AnalyticsData,
    AnalyticsFetchRequest,
    CommentReplyRequest,
    CommentReplyResult,
    DMRequest,
    DMResult,
    ExtractionResult,
    ExtractionSchema,
    Platform,
    PlatformAPIRequest,
    PlatformAPIResponse,
    PostContentRequest,
    PostContentResult,
    ProviderType,
    SkillRequest,
    SkillResult,
    TrendingFetchRequest,
    TrendingItem,
)
from .base import BrowserProvider

_FIXTURE_TRENDING: dict[Platform, list[dict[str, Any]]] = {
    Platform.TIKTOK: [
        {"audio_title": "Espresso", "audio_author": "Sabrina Carpenter",
         "usage_count": 2_400_000, "growth_rate_pct": 340.0},
        {"audio_title": "I Had Some Help", "audio_author": "Post Malone ft. Morgan Wallen",
         "usage_count": 1_900_000, "growth_rate_pct": 210.0},
        {"audio_title": "Too Sweet", "audio_author": "Hozier",
         "usage_count": 1_200_000, "growth_rate_pct": 180.0},
    ],
    Platform.INSTAGRAM: [
        {"audio_title": "Cruel Summer", "audio_author": "Taylor Swift",
         "usage_count": 800_000, "growth_rate_pct": 95.0},
        {"audio_title": "Levitating", "audio_author": "Dua Lipa",
         "usage_count": 650_000, "growth_rate_pct": 70.0},
    ],
}


class MockProvider(BrowserProvider):
    """
    Fully controllable mock for tests and offline demos.

    Test assertions:
        provider = MockProvider()
        result = await provider.run_agent_task(task)
        assert provider.calls["run_agent_task"][0]["task_id"] == task.task_id
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._audit = get_audit()
        self.calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._failures: dict[str, Exception] = {}

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.MOCK

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def inject_failure(self, operation: str, exc: Exception) -> None:
        """Force the named operation to raise exc on next call."""
        self._failures[operation] = exc

    def _maybe_fail(self, operation: str) -> None:
        if operation in self._failures:
            exc = self._failures.pop(operation)
            raise exc

    # ------------------------------------------------------------------
    # BrowserProvider implementation
    # ------------------------------------------------------------------

    async def run_agent_task(self, task: AgentTask) -> AgentResult:
        self._assert_not_killed()
        self._maybe_fail("run_agent_task")
        t0 = time.monotonic()
        self._audit.log_request("mock", "run_agent_task", task.task_id, task.dry_run)
        self.calls["run_agent_task"].append(task.model_dump())

        result = AgentResult(
            task_id=task.task_id,
            success=True,
            provider=ProviderType.MOCK,
            duration_seconds=round(time.monotonic() - t0, 3),
            steps_taken=min(task.max_steps, 3),
            output={"mock": True, "description_echo": task.description[:80]},
            dry_run=task.dry_run or self._dry_run,
        )
        self._audit.log_result("mock", "run_agent_task", task.task_id, True, result.dry_run)
        return result

    async def bulk_extract(
        self,
        urls: list[str],
        schema: ExtractionSchema,
    ) -> list[ExtractionResult]:
        self._assert_not_killed()
        self._maybe_fail("bulk_extract")
        results = []
        for url in urls:
            self.calls["bulk_extract"].append({"url": url, "schema": schema.model_dump()})
            data = {field: f"[mock_{field}_from_{url[:30]}]" for field in schema.fields}
            results.append(ExtractionResult(url=url, success=True, data=data))
        self._audit.log("mock.bulk_extract", {"url_count": len(urls)})
        return results

    async def invoke_skill(self, request: SkillRequest) -> SkillResult:
        self._assert_not_killed()
        self._maybe_fail("invoke_skill")
        self.calls["invoke_skill"].append(request.model_dump())
        result = SkillResult(
            request_id=request.request_id,
            skill_name=request.skill_name,
            success=True,
            result={"mock": True, "skill": request.skill_name, "params_echo": request.params},
        )
        self._audit.log("mock.invoke_skill", {"skill": request.skill_name})
        return result

    async def call_platform_api(self, request: PlatformAPIRequest) -> PlatformAPIResponse:
        self._assert_not_killed(request.platform.value)
        self._maybe_fail("call_platform_api")
        self.calls["call_platform_api"].append(request.model_dump())
        response = PlatformAPIResponse(
            request_id=request.request_id,
            platform=request.platform,
            status_code=200,
            data={"mock": True, "endpoint": request.endpoint},
            dry_run=request.dry_run or self._dry_run,
        )
        self._audit.log("mock.call_platform_api", {"platform": request.platform, "endpoint": request.endpoint})
        return response

    # ------------------------------------------------------------------
    # Adapter-level helpers (called by MockAdapters)
    # ------------------------------------------------------------------

    async def post_content(self, request: PostContentRequest) -> PostContentResult:
        self._assert_not_killed(request.platform.value)
        self._maybe_fail("post_content")
        self.calls["post_content"].append(request.model_dump())
        dry = request.dry_run or self._dry_run
        post_id = ("DRY-RUN-" if dry else "") + str(uuid.uuid4())[:8]
        result = PostContentResult(
            request_id=request.request_id,
            platform=request.platform,
            success=True,
            post_id=post_id,
            post_url=f"https://{request.platform.value}.com/p/{post_id}",
            posted_at=None if dry else datetime.now(UTC),
            dry_run=dry,
        )
        self._audit.log_result("mock", "post_content", request.request_id, True, dry)
        return result

    async def reply_comment(self, request: CommentReplyRequest) -> CommentReplyResult:
        self._assert_not_killed(request.platform.value)
        self._maybe_fail("reply_comment")
        self.calls["reply_comment"].append(request.model_dump())
        dry = request.dry_run or self._dry_run
        reply_id = ("DRY-RUN-" if dry else "") + str(uuid.uuid4())[:8]
        result = CommentReplyResult(
            request_id=request.request_id,
            platform=request.platform,
            success=True,
            reply_id=reply_id,
            dry_run=dry,
        )
        self._audit.log_result("mock", "reply_comment", request.request_id, True, dry)
        return result

    async def send_dm(self, request: DMRequest) -> DMResult:
        self._assert_not_killed(request.platform.value)
        self._maybe_fail("send_dm")
        self.calls["send_dm"].append(request.model_dump())
        dry = request.dry_run or self._dry_run
        message_id = ("DRY-RUN-" if dry else "") + str(uuid.uuid4())[:8]
        result = DMResult(
            request_id=request.request_id,
            platform=request.platform,
            success=True,
            message_id=message_id,
            dry_run=dry,
        )
        self._audit.log_result("mock", "send_dm", request.request_id, True, dry)
        return result

    async def fetch_analytics(self, request: AnalyticsFetchRequest) -> AnalyticsData:
        self._assert_not_killed(request.platform.value)
        self._maybe_fail("fetch_analytics")
        self.calls["fetch_analytics"].append(request.model_dump())
        result = AnalyticsData(
            request_id=request.request_id,
            platform=request.platform,
            post_id=request.post_id,
            views=42_000,
            likes=3_800,
            comments=210,
            shares=540,
            saves=980,
            follows_gained=120,
            watch_time_avg_seconds=18.4,
            completion_rate_pct=62.5,
        )
        self._audit.log("mock.fetch_analytics", {"platform": request.platform, "post_id": request.post_id})
        return result

    async def fetch_trending(self, request: TrendingFetchRequest) -> list[TrendingItem]:
        self._assert_not_killed(request.platform.value)
        self._maybe_fail("fetch_trending")
        self.calls["fetch_trending"].append(request.model_dump())
        fixtures = _FIXTURE_TRENDING.get(request.platform, [])
        items = [
            TrendingItem(platform=request.platform, **f)
            for f in fixtures[: request.limit]
        ]
        self._audit.log("mock.fetch_trending", {"platform": request.platform, "count": len(items)})
        return items
