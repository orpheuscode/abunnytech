from __future__ import annotations

import httpx
import pytest

from hackathon_pipelines.adapters.instagram_download_api import (
    InstagramDownloadAPI,
    InstagramDownloadAPIConfig,
    _pick_media_url,
)


def test_pick_media_url_supports_common_response_shapes() -> None:
    assert _pick_media_url({"media_url": "https://cdn.example.com/a.mp4"}) == "https://cdn.example.com/a.mp4"
    assert _pick_media_url({"result": {"download_url": "https://cdn.example.com/b.mp4"}}) == "https://cdn.example.com/b.mp4"
    assert _pick_media_url({"data": {"video_url": "https://cdn.example.com/c.mp4"}}) == "https://cdn.example.com/c.mp4"
    assert _pick_media_url({"unexpected": "shape"}) is None


@pytest.mark.asyncio
async def test_instagram_download_api_posts_and_normalizes_media_url() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={"result": {"download_url": "https://cdn.example.com/reel.mp4"}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    api = InstagramDownloadAPI(
        config=InstagramDownloadAPIConfig(
            api_url="https://api.example.com/download",
            api_key="secret",
            request_method="POST",
        ),
        client=client,
    )

    response = await api.resolve_media_url(
        source_url="https://www.instagram.com/reels/ABC123/",
        reel_id="ABC123",
    )

    await client.aclose()

    assert captured["method"] == "POST"
    assert "Bearer secret" in str(captured["headers"])
    assert response.media_url == "https://cdn.example.com/reel.mp4"
