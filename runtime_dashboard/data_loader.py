"""Data loader that reads from fixture JSON or a live API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from runtime_dashboard.owner_data_store import load_fixture_collection

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "demo_seed.json"

_PLACEHOLDER_TRENDING_AUDIO = {
    ("audio_001", "Chill Beats Lo-fi", "LofiGirl"),
    ("audio_002", "Hype Trap Intro", "BeatMaster"),
}
_PLACEHOLDER_BLUEPRINT_TITLES = {
    "5 AI Tools You Need in 2026",
    "How I Automated My Morning Routine with AI",
}
_PLACEHOLDER_CONTENT_CAPTIONS = {
    "5 AI tools that changed my workflow 🤖",
}
_PLACEHOLDER_DISTRIBUTION_URLS = {
    "https://tiktok.com/@techtok_sarah/video/demo",
    "https://tiktok.com/@techtok_sarah/video/demo_001",
}
_PLACEHOLDER_DIRECTIVE_SUMMARIES = {
    "Improve hook and shorten intro for better retention",
}
_PLACEHOLDER_DIRECTIVE_TYPES = {
    ("increase_hook_strength", "shorten_intro"),
    ("increase_hook_strength", "shorten_intro", "add_captions"),
}
_PLACEHOLDER_PRODUCT_NAMES = {
    "Creator Toolkit eBook",
}
_PLACEHOLDER_PRODUCT_HOSTS = {
    "store.example.com",
}
_PLACEHOLDER_CONTENT_HOSTS = {
    "cdn.example.com",
}


def _url_host(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return urlparse(text).netloc.lower()


def _directive_types(item: dict[str, Any]) -> tuple[str, ...]:
    directives = item.get("directives")
    if not isinstance(directives, list):
        return ()
    return tuple(
        str(directive.get("type") or "").strip().lower()
        for directive in directives
        if isinstance(directive, dict)
    )


def _is_placeholder_trending_audio(item: dict[str, Any]) -> bool:
    signature = (
        str(item.get("audio_id") or "").strip(),
        str(item.get("title") or "").strip(),
        str(item.get("artist") or "").strip(),
    )
    return signature in _PLACEHOLDER_TRENDING_AUDIO


def _is_placeholder_video_blueprint(item: dict[str, Any]) -> bool:
    title = str(item.get("title") or "").strip()
    return title in _PLACEHOLDER_BLUEPRINT_TITLES


def _is_placeholder_content_package(item: dict[str, Any]) -> bool:
    caption = str(item.get("caption") or "").strip()
    video_host = _url_host(item.get("video_url"))
    thumb_host = _url_host(item.get("thumbnail_url"))
    return (
        caption in _PLACEHOLDER_CONTENT_CAPTIONS
        or video_host in _PLACEHOLDER_CONTENT_HOSTS
        or thumb_host in _PLACEHOLDER_CONTENT_HOSTS
    )


def _is_placeholder_distribution_record(item: dict[str, Any]) -> bool:
    post_url = str(item.get("post_url") or "").strip()
    return post_url in _PLACEHOLDER_DISTRIBUTION_URLS


def _is_placeholder_optimization_directive(item: dict[str, Any]) -> bool:
    summary = str(item.get("summary") or "").strip()
    return summary in _PLACEHOLDER_DIRECTIVE_SUMMARIES or _directive_types(
        item
    ) in _PLACEHOLDER_DIRECTIVE_TYPES


def _is_placeholder_redo_queue_item(item: dict[str, Any]) -> bool:
    return (
        str(item.get("reason") or "").strip() == "Low watch-time on first 3s"
        and int(item.get("priority") or 0) == 1
        and str(item.get("status") or "").strip().lower() == "pending"
    )


def _is_placeholder_product(item: dict[str, Any]) -> bool:
    name = str(item.get("name") or "").strip()
    url_host = _url_host(item.get("url"))
    return name in _PLACEHOLDER_PRODUCT_NAMES or url_host in _PLACEHOLDER_PRODUCT_HOSTS


_PLACEHOLDER_MATCHERS: dict[str, Any] = {
    "trending_audio": _is_placeholder_trending_audio,
    "video_blueprints": _is_placeholder_video_blueprint,
    "content_packages": _is_placeholder_content_package,
    "distribution_records": _is_placeholder_distribution_record,
    "optimization_directives": _is_placeholder_optimization_directive,
    "redo_queue": _is_placeholder_redo_queue_item,
    "product_catalog": _is_placeholder_product,
}


def _load_fixture(key: str) -> list[dict[str, Any]]:
    with _FIXTURE_PATH.open() as f:
        data = json.load(f)
    return data.get(key, [])


def filter_placeholder_items(key: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matcher = _PLACEHOLDER_MATCHERS.get(key)
    if matcher is None:
        return items
    return [item for item in items if not matcher(item)]


def _fetch_api(api_base: str, path: str) -> Any:
    resp = httpx.get(f"{api_base}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def load_identities(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return load_fixture_collection("identities")
    return _fetch_api(api_base, "/identity_matrix")


def load_trending_audio(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        items = _load_fixture("trending_audio")
    else:
        items = _fetch_api(api_base, "/trending_audio")
    return filter_placeholder_items("trending_audio", items)


def load_video_blueprints(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        items = _load_fixture("video_blueprints")
    else:
        items = _fetch_api(api_base, "/video_blueprints")
    return filter_placeholder_items("video_blueprints", items)


def load_content_packages(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        items = _load_fixture("content_packages")
    else:
        items = _fetch_api(api_base, "/content_packages")
    return filter_placeholder_items("content_packages", items)


def load_distribution_records(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        items = _load_fixture("distribution_records")
    else:
        items = _fetch_api(api_base, "/distribution_records")
    return filter_placeholder_items("distribution_records", items)


def load_pipeline_posts(control_plane_base: str | None) -> list[dict[str, Any]]:
    if not control_plane_base:
        return []
    payload = _fetch_api(control_plane_base, "/pipeline/posts")
    return payload.get("posts", []) if isinstance(payload, dict) else []


def load_optimization_directives(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        items = _load_fixture("optimization_directives")
    else:
        items = _fetch_api(api_base, "/optimization_directives")
    return filter_placeholder_items("optimization_directives", items)


def load_redo_queue(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        items = _load_fixture("redo_queue")
    else:
        items = _fetch_api(api_base, "/redo_queue")
    return filter_placeholder_items("redo_queue", items)


def load_competitor_watchlist(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("competitor_watchlist")
    return _fetch_api(api_base, "/competitor_watchlist")


def load_product_catalog(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        items = load_fixture_collection("product_catalog")
    else:
        items = _fetch_api(api_base, "/product_catalog")
    return filter_placeholder_items("product_catalog", items)
