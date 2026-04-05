"""API-backed Instagram reel downloader used after Browser Use discovery."""

from __future__ import annotations

import os
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field


class InstagramDownloadAPIConfig(BaseModel):
    """Configuration for a generic HTTP API that resolves reel URLs to downloadable media URLs."""

    model_config = ConfigDict(extra="forbid")

    api_url: str
    api_key: str | None = None
    auth_header_name: str = "Authorization"
    auth_scheme_prefix: str = "Bearer "
    request_method: Literal["GET", "POST"] = "POST"
    source_url_field: str = "url"
    reel_id_field: str = "reel_id"
    timeout_seconds: float = Field(default=60.0, ge=1.0)


class InstagramDownloadRequest(BaseModel):
    """Payload sent to the reel download API."""

    model_config = ConfigDict(extra="forbid")

    url: str
    reel_id: str


class InstagramDownloadResponse(BaseModel):
    """Normalized response returned by the reel download API."""

    model_config = ConfigDict(extra="forbid")

    media_url: str
    raw_payload: dict


def _pick_media_url(payload: dict) -> str | None:
    """Best-effort extraction across common downloader API response shapes."""

    candidate_keys = (
        "media_url",
        "download_url",
        "video_url",
        "mp4_url",
        "url",
    )
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value

    nested_paths = (
        ("data", "media_url"),
        ("data", "download_url"),
        ("data", "video_url"),
        ("data", "mp4_url"),
        ("data", "url"),
        ("result", "media_url"),
        ("result", "download_url"),
        ("result", "video_url"),
        ("result", "mp4_url"),
        ("result", "url"),
    )
    for first, second in nested_paths:
        outer = payload.get(first)
        if isinstance(outer, dict):
            value = outer.get(second)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    return None


class InstagramDownloadAPI:
    """Thin client for a generic reel-download API."""

    def __init__(
        self,
        *,
        config: InstagramDownloadAPIConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or self.from_env()
        self._client = client

    @staticmethod
    def from_env() -> InstagramDownloadAPIConfig:
        api_url = os.getenv("INSTAGRAM_DOWNLOADER_API_URL", "").strip()
        if not api_url:
            msg = "INSTAGRAM_DOWNLOADER_API_URL is not set"
            raise RuntimeError(msg)
        return InstagramDownloadAPIConfig(
            api_url=api_url,
            api_key=os.getenv("INSTAGRAM_DOWNLOADER_API_KEY") or None,
            auth_header_name=os.getenv("INSTAGRAM_DOWNLOADER_AUTH_HEADER", "Authorization"),
            auth_scheme_prefix=os.getenv("INSTAGRAM_DOWNLOADER_AUTH_PREFIX", "Bearer "),
            request_method=os.getenv("INSTAGRAM_DOWNLOADER_REQUEST_METHOD", "POST").upper(),
            source_url_field=os.getenv("INSTAGRAM_DOWNLOADER_SOURCE_URL_FIELD", "url"),
            reel_id_field=os.getenv("INSTAGRAM_DOWNLOADER_REEL_ID_FIELD", "reel_id"),
            timeout_seconds=float(os.getenv("INSTAGRAM_DOWNLOADER_TIMEOUT_SECONDS", "60")),
        )

    async def resolve_media_url(self, *, source_url: str, reel_id: str) -> InstagramDownloadResponse:
        request_payload = InstagramDownloadRequest(url=source_url, reel_id=reel_id)
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers[self._config.auth_header_name] = f"{self._config.auth_scheme_prefix}{self._config.api_key}"

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._config.timeout_seconds)
        try:
            if self._config.request_method == "GET":
                response = await client.get(
                    self._config.api_url,
                    params={
                        self._config.source_url_field: request_payload.url,
                        self._config.reel_id_field: request_payload.reel_id,
                    },
                    headers=headers,
                )
            else:
                response = await client.post(
                    self._config.api_url,
                    json={
                        self._config.source_url_field: request_payload.url,
                        self._config.reel_id_field: request_payload.reel_id,
                    },
                    headers=headers,
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                msg = "Downloader API returned a non-object JSON payload."
                raise RuntimeError(msg)
            media_url = _pick_media_url(payload)
            if not media_url:
                msg = "Downloader API response did not include a downloadable media URL."
                raise RuntimeError(msg)
            return InstagramDownloadResponse(media_url=media_url, raw_payload=payload)
        finally:
            if owns_client:
                await client.aclose()
