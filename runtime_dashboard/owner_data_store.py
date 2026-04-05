"""Local writable store for owner-dashboard fixture mode.

This keeps dashboard edits out of the checked-in fixture JSON while still
allowing the UI to feel stateful when the user runs in demo mode.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "demo_seed.json"
_OVERRIDE_PATH = Path(__file__).resolve().parent / ".owner_dashboard_data.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_fixture_collection(key: str) -> list[dict[str, Any]]:
    overrides = _read_json(_OVERRIDE_PATH)
    override_items = overrides.get(key)
    if isinstance(override_items, list):
        return override_items

    fixtures = _read_json(_FIXTURE_PATH)
    base_items = fixtures.get(key)
    return base_items if isinstance(base_items, list) else []


def save_fixture_collection(key: str, items: list[dict[str, Any]]) -> None:
    overrides = _read_json(_OVERRIDE_PATH)
    overrides[key] = items
    _write_json(_OVERRIDE_PATH, overrides)


def update_fixture_identity_avatar(identity_id: str, avatar_url: str) -> dict[str, Any] | None:
    identities = list(load_fixture_collection("identities"))
    for identity in identities:
        if str(identity.get("id", "")) != identity_id:
            continue
        avatar = identity.get("avatar")
        if not isinstance(avatar, dict):
            avatar = {}
        avatar["avatar_url"] = avatar_url
        identity["avatar"] = avatar
        save_fixture_collection("identities", identities)
        return identity
    return None


def create_fixture_product(product: dict[str, Any]) -> dict[str, Any]:
    products = list(load_fixture_collection("product_catalog"))
    products.insert(0, product)
    save_fixture_collection("product_catalog", products)
    return product


def delete_fixture_product(*, name: str, image_url: str = "") -> dict[str, Any] | None:
    products = list(load_fixture_collection("product_catalog"))
    for index, product in enumerate(products):
        if str(product.get("name") or "") != name:
            continue
        if image_url and str(product.get("image_url") or "") != image_url:
            continue
        removed = products.pop(index)
        save_fixture_collection("product_catalog", products)
        return removed
    return None
