"""
PlatformAPIProvider — routes calls through official platform REST APIs.

Use this when an official API exists and browser automation is not needed.
Falls back cleanly when credentials are absent (raises with a clear message).

Supported:
  TikTok: TikTok for Developers (Content Posting API)
  Instagram: Instagram Graph API
  Shopify: Admin REST API
  Analytics: (no official realtime API — use adapter-specific polling)

Status: STUB — set platform credential env vars to activate.
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
    Platform,
    PlatformAPIRequest,
    PlatformAPIResponse,
    ProviderType,
    SkillRequest,
    SkillResult,
)
from .base import BrowserProvider

_PLATFORM_BASE_URLS: dict[Platform, str] = {
    Platform.INSTAGRAM: "https://graph.instagram.com",
    Platform.TIKTOK: "https://open.tiktokapis.com",
    Platform.SHOPIFY: "",   # Requires store-specific URL: https://{store}.myshopify.com/admin/api/2024-01
    Platform.ANALYTICS: "",
}

_PLATFORM_TOKEN_ENV: dict[Platform, str] = {
    Platform.INSTAGRAM: "INSTAGRAM_ACCESS_TOKEN",
    Platform.TIKTOK: "TIKTOK_ACCESS_TOKEN",
    Platform.SHOPIFY: "SHOPIFY_ADMIN_TOKEN",
    Platform.ANALYTICS: "",
}


class PlatformAPIProvider(BrowserProvider):
    """
    Routes PlatformAPIRequest objects to official platform REST APIs via httpx.

    Credentials are read from environment variables at call time.
    dry_run=True short-circuits all calls and returns mock 200 responses.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._audit = get_audit()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.PLATFORM_API

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    async def run_agent_task(self, task: AgentTask) -> AgentResult:
        raise NotImplementedError("PlatformAPIProvider: use BrowserUseProvider for agent tasks.")

    async def bulk_extract(self, urls: list[str], schema: ExtractionSchema) -> list[ExtractionResult]:
        raise NotImplementedError("PlatformAPIProvider: use CodeAgentProvider for bulk extraction.")

    async def invoke_skill(self, request: SkillRequest) -> SkillResult:
        raise NotImplementedError("PlatformAPIProvider: use SkillAPIProvider for skill invocations.")

    async def call_platform_api(self, request: PlatformAPIRequest) -> PlatformAPIResponse:
        self._assert_not_killed(request.platform.value)
        t0 = time.monotonic()
        self._audit.log_request(
            "platform_api", f"{request.platform.value}.{request.method}",
            request.request_id, request.dry_run,
            extra={"endpoint": request.endpoint},
        )

        dry = request.dry_run or self._dry_run
        if dry:
            resp = PlatformAPIResponse(
                request_id=request.request_id,
                platform=request.platform,
                status_code=200,
                data={"dry_run": True, "endpoint": request.endpoint},
                dry_run=True,
            )
            self._audit.log_result(
                "platform_api", f"{request.platform.value}.call",
                request.request_id, True, True,
            )
            return resp

        base_url = _PLATFORM_BASE_URLS.get(request.platform, "")
        if not base_url:
            raise RuntimeError(
                f"No base URL configured for platform {request.platform}. "
                "Set it via platform config or use dry_run=True."
            )

        token_env = _PLATFORM_TOKEN_ENV.get(request.platform, "")
        token = os.getenv(token_env, "") if token_env else ""
        if not token:
            raise RuntimeError(
                f"Missing credential for {request.platform}: set {token_env} env var."
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            http_method = getattr(client, request.method.lower())
            response = await http_method(
                request.endpoint,
                params=request.params or None,
                json=request.body or None,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        result = PlatformAPIResponse(
            request_id=request.request_id,
            platform=request.platform,
            status_code=response.status_code,
            data=data,
            duration_ms=elapsed,
            dry_run=False,
        )
        self._audit.log_result(
            "platform_api", f"{request.platform.value}.call",
            request.request_id, True, False,
            extra={"status_code": response.status_code, "duration_ms": elapsed},
        )
        return result
