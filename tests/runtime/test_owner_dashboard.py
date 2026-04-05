from __future__ import annotations

import io

from runtime_dashboard import flask_owner_app as dashboard
from runtime_dashboard.data_loader import load_identities
from runtime_dashboard.owner_data_store import load_fixture_collection


def _build_client(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "_UPLOAD_DIR", tmp_path / "uploads")

    from runtime_dashboard import owner_data_store

    monkeypatch.setattr(owner_data_store, "_OVERRIDE_PATH", tmp_path / ".owner_dashboard_data.json")
    app = dashboard.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_upload_identity_avatar_in_fixture_mode(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    identity_id = load_identities(None)[0]["id"]

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/avatars/upload",
        data={
            "next": "/identity",
            "avatar_file": (io.BytesIO(b"avatar-bytes"), "avatar.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Avatar added to the library folder." in resp.data

    identities = load_fixture_collection("identities")
    updated = next(item for item in identities if item["id"] == identity_id)
    assert updated["avatar"]["avatar_url"].startswith("/static/uploads/avatars/avatar-")
    assert any((tmp_path / "uploads" / "avatars").iterdir())


def test_create_product_with_image_and_description_in_fixture_mode(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/catalog/products",
        data={
            "next": "/catalog",
            "name": "Studio Light Kit",
            "description": "Soft light bundle for cleaner product demos.",
            "price": "29.99",
            "url": "https://store.example.com/light-kit",
            "affiliate_code": "BUNNY10",
            "active": "1",
            "product_image": (io.BytesIO(b"product-bytes"), "light-kit.webp"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Product saved: Studio Light Kit" in resp.data

    products = load_fixture_collection("product_catalog")
    created = next(item for item in products if item["name"] == "Studio Light Kit")
    assert created["description"] == "Soft light bundle for cleaner product demos."
    assert created["price_cents"] == 2999
    assert created["image_url"].startswith("/static/uploads/products/product-")
    assert created["identity_id"] is None
    assert any((tmp_path / "uploads" / "products").iterdir())


def test_create_product_requires_description(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/catalog/products",
        data={"next": "/catalog", "name": "No Description"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Add a product description before saving." in resp.data

    products = load_fixture_collection("product_catalog")
    assert all(item.get("name") != "No Description" for item in products)


def test_demo_run_gemini_orchestrator_flashes_result(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    def fake_post_json(api_base: str, path: str, payload: dict):
        assert path == "/pipeline/gemini-orchestrate"
        assert payload["instruction"] == "Run the full pipeline"
        return {"final_text": "Gemini orchestration completed."}

    monkeypatch.setattr(dashboard, "_post_json", fake_post_json)

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/demo/run-gemini-orchestrator",
        data={"instruction": "Run the full pipeline"},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Gemini orchestration completed." in resp.data


def test_demo_page_shows_loop_status(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    def fake_get_json(api_base: str, path: str):
        assert path == "/pipeline/loop/status"
        return {
            "running": True,
            "configured": True,
            "cycle_count": 4,
            "last_started_at": "2026-04-04T10:00:00Z",
            "last_finished_at": "2026-04-04T10:05:00Z",
            "next_run_at": "2026-04-04T10:10:00Z",
            "last_error": None,
        }

    monkeypatch.setattr(dashboard, "_get_json", fake_get_json)

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.get("/demo")
    assert resp.status_code == 200
    assert b"Run Gemini Orchestrator" in resp.data
    assert b"Stop Pipeline Loop" in resp.data
    assert b"Cycles: 4" in resp.data
