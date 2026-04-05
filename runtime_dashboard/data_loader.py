"""Data loader that reads from fixture JSON or a live API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "demo_seed.json"


def _load_fixture(key: str) -> list[dict[str, Any]]:
    with _FIXTURE_PATH.open() as f:
        data = json.load(f)
    return data.get(key, [])


def _fetch_api(api_base: str, path: str) -> list[dict[str, Any]]:
    resp = httpx.get(f"{api_base}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def load_identities(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("identities")
    return _fetch_api(api_base, "/identity_matrix")


def load_trending_audio(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("trending_audio")
    return _fetch_api(api_base, "/trending_audio")


def load_video_blueprints(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("video_blueprints")
    return _fetch_api(api_base, "/video_blueprints")


def load_content_packages(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("content_packages")
    return _fetch_api(api_base, "/content_packages")


def load_distribution_records(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("distribution_records")
    return _fetch_api(api_base, "/distribution_records")


def load_optimization_directives(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("optimization_directives")
    return _fetch_api(api_base, "/optimization_directives")


def load_redo_queue(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("redo_queue")
    return _fetch_api(api_base, "/redo_queue")


def load_competitor_watchlist(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("competitor_watchlist")
    return _fetch_api(api_base, "/competitor_watchlist")


def load_product_catalog(api_base: str | None) -> list[dict[str, Any]]:
    if api_base is None:
        return _load_fixture("product_catalog")
    return _fetch_api(api_base, "/product_catalog")
