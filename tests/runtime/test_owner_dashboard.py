from __future__ import annotations

import io
import os

import httpx

from runtime_dashboard import flask_owner_app as dashboard
from runtime_dashboard import secrets_store
from runtime_dashboard.data_loader import load_identities
from runtime_dashboard.owner_data_store import load_fixture_collection


def _build_client(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "_UPLOAD_DIR", tmp_path / "uploads")

    from runtime_dashboard import owner_data_store

    monkeypatch.setattr(owner_data_store, "_OVERRIDE_PATH", tmp_path / ".owner_dashboard_data.json")
    monkeypatch.setattr(secrets_store, "_STORE_PATH", tmp_path / ".owner_secrets.json")
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


def test_select_avatar_library_asset_is_used_for_generation(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    avatar_dir = tmp_path / "uploads" / "avatars"
    avatar_dir.mkdir(parents=True)
    selected_avatar = avatar_dir / "selected.png"
    selected_avatar.write_bytes(b"avatar")

    async def fake_wait_for_cdp(*args, **kwargs):
        return True

    def fake_post_json(api_base: str, path: str, payload: dict):
        assert path == "/pipeline/generate-video"
        assert payload["avatar_image_path"] == str(selected_avatar.resolve())
        return {"run": {"status": "ready", "selected_template_id": "tpl_x", "video_path": "/tmp/out.mp4"}}

    monkeypatch.setattr(dashboard, "_post_json", fake_post_json)
    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "environment",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "",
            "chrome_user_data_dir": "",
            "chrome_profile_directory": "",
            "headless": False,
        },
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    client.post(
        "/avatars/select",
        data={"asset_path": str(selected_avatar.resolve()), "next": "/identity"},
        follow_redirects=True,
    )
    resp = client.post("/demo/generate-video", data={"run_mode": "live_visible"}, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Generated a new video from the stored video structure database." in resp.data


def test_delete_avatar_library_asset_removes_file(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    avatar_dir = tmp_path / "uploads" / "avatars"
    avatar_dir.mkdir(parents=True)
    avatar = avatar_dir / "avatar.png"
    avatar.write_bytes(b"avatar")

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/avatars/delete",
        data={"asset_path": str(avatar.resolve()), "next": "/identity"},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Avatar removed: avatar.png" in resp.data
    assert not avatar.exists()


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


def test_select_product_is_used_for_generation(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    product_dir = tmp_path / "uploads" / "products"
    product_dir.mkdir(parents=True)
    selected_image = product_dir / "product.png"
    selected_image.write_bytes(b"product")

    client.post(
        "/catalog/products",
        data={
            "next": "/catalog",
            "name": "Selected Product",
            "description": "Use this product for generation.",
            "price": "19.99",
            "product_image": (io.BytesIO(b"product-bytes"), "product.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    products = load_fixture_collection("product_catalog")
    selected = next(item for item in products if item["name"] == "Selected Product")

    async def fake_wait_for_cdp(*args, **kwargs):
        return True

    def fake_post_json(api_base: str, path: str, payload: dict):
        assert path == "/pipeline/generate-video"
        assert payload["product_title"] == "Selected Product"
        assert payload["product_image_path"].endswith(".png")
        return {"run": {"status": "ready", "selected_template_id": "tpl_x", "video_path": "/tmp/out.mp4"}}

    monkeypatch.setattr(dashboard, "_post_json", fake_post_json)
    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "environment",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "",
            "chrome_user_data_dir": "",
            "chrome_profile_directory": "",
            "headless": False,
        },
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    client.post(
        "/catalog/products/select",
        data={"product_key": selected["image_url"], "next": "/catalog"},
        follow_redirects=True,
    )
    resp = client.post("/demo/generate-video", data={"run_mode": "live_visible"}, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Generated a new video from the stored video structure database." in resp.data


def test_delete_catalog_product_removes_fixture_entry(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    client.post(
        "/catalog/products",
        data={
            "next": "/catalog",
            "name": "Delete Me",
            "description": "Temporary product.",
            "price": "5.00",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    resp = client.post(
        "/catalog/products/delete",
        data={"name": "Delete Me", "image_url": "", "next": "/catalog"},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Product removed: Delete Me" in resp.data
    products = load_fixture_collection("product_catalog")
    assert all(item.get("name") != "Delete Me" for item in products)


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


def test_dashboard_hides_placeholder_fixture_rows(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    discovery = client.get("/discovery")
    assert discovery.status_code == 200
    assert b"Chill Beats Lo-fi" not in discovery.data
    assert b"Hype Trap Intro" not in discovery.data
    assert b"No trending audio discovered yet." in discovery.data

    content = client.get("/content")
    assert content.status_code == 200
    assert b"5 AI Tools You Need in 2026" not in content.data
    assert b"No video blueprints generated yet." in content.data
    assert b"No content packages assembled yet." in content.data

    distribution = client.get("/distribution")
    assert distribution.status_code == 200
    assert b"techtok_sarah" not in distribution.data
    assert b"No distribution records yet. Run the pipeline to post content." in distribution.data

    analytics = client.get("/analytics")
    assert analytics.status_code == 200
    assert b"Increase Hook Strength" not in analytics.data
    assert b"Low watch-time on first 3s" not in analytics.data
    assert b"No optimization directives generated yet." in analytics.data
    assert b"Redo queue is empty" in analytics.data

    catalog = client.get("/catalog")
    assert catalog.status_code == 200
    assert b"Creator Toolkit eBook" not in catalog.data
    assert b"No products in the storefront yet." in catalog.data


def test_dashboard_backfills_live_empty_sections_with_fixture_data(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    monkeypatch.setattr(dashboard, "load_trending_audio", lambda api: [])
    monkeypatch.setattr(dashboard, "load_competitor_watchlist", lambda api: [])
    monkeypatch.setattr(dashboard, "load_video_blueprints", lambda api: [])
    monkeypatch.setattr(dashboard, "load_content_packages", lambda api: [])
    monkeypatch.setattr(dashboard, "load_distribution_records", lambda api: [])
    monkeypatch.setattr(dashboard, "load_pipeline_posts", lambda base: [])
    monkeypatch.setattr(dashboard, "load_optimization_directives", lambda api: [])
    monkeypatch.setattr(dashboard, "load_redo_queue", lambda api: [])
    monkeypatch.setattr(dashboard, "load_product_catalog", lambda api: [])
    monkeypatch.setattr(
        dashboard,
        "_get_json",
        lambda api_base, path: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = False
        sess["api_base"] = "http://localhost:8000"

    discovery = client.get("/discovery")
    assert discovery.status_code == 200
    assert b"Chill Beats Lo-fi" in discovery.data
    assert b"@rival_creator" in discovery.data

    content = client.get("/content")
    assert content.status_code == 200
    assert b"5 AI Tools You Need in 2026" in content.data
    assert b"5 AI tools that changed my workflow" in content.data

    distribution = client.get("/distribution")
    assert distribution.status_code == 200
    assert b"techtok_sarah" in distribution.data
    assert b"Replies logged: 2" in distribution.data

    analytics = client.get("/analytics")
    assert analytics.status_code == 200
    assert b"Increase Hook Strength" in analytics.data
    assert b"Low watch-time on first 3s" in analytics.data

    catalog = client.get("/catalog")
    assert catalog.status_code == 200
    assert b"Creator Toolkit eBook" in catalog.data


def test_demo_run_gemini_orchestrator_flashes_result(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    async def fake_wait_for_cdp(*args, **kwargs):
        return True

    def fake_post_json(api_base: str, path: str, payload: dict):
        assert path == "/pipeline/gemini-orchestrate"
        assert payload["instruction"] == "Run the full pipeline"
        assert payload["dry_run"] is False
        assert payload["browser_runtime"]["cdp_url"] == "http://127.0.0.1:9222"
        return {"final_text": "Gemini orchestration completed."}

    monkeypatch.setattr(dashboard, "_post_json", fake_post_json)
    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "environment",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "",
            "chrome_user_data_dir": "",
            "chrome_profile_directory": "",
            "headless": False,
        },
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/demo/run-gemini-orchestrator",
        data={"instruction": "Run the full pipeline", "run_mode": "live_visible"},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Gemini orchestration completed." in resp.data


def test_demo_page_shows_loop_status(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    def fake_get_json(api_base: str, path: str):
        if path == "/pipeline/loop/status":
            return {
                "running": True,
                "configured": True,
                "cycle_count": 4,
                "last_started_at": "2026-04-04T10:00:00Z",
                "last_finished_at": "2026-04-04T10:05:00Z",
                "next_run_at": "2026-04-04T10:10:00Z",
                "last_error": None,
            }
        assert path == "/pipeline/latest-run"
        return {
            "run": {
                "run_id": "run_123",
                "status": "ready",
                "caption": "Latest caption",
                "product_title": "Studio Light Kit",
                "product_description": "Soft light bundle for cleaner demos.",
                "reels_discovered": 5,
                "reels_queued": 4,
                "structures_persisted": 4,
                "selected_template_id": "tpl_123",
                "video_path": None,
                "avatar_image_path": None,
                "product_image_path": None,
                "engagement_summary": {
                    "status": "replied",
                    "total_replies_logged": 2,
                    "last_run_at": "2026-04-04T10:06:00Z",
                    "recent_replies": [
                        {"commenter_handle": "shopper01", "response_text": "link in bio ✨"}
                    ],
                },
            }
        }

    monkeypatch.setattr(dashboard, "_get_json", fake_get_json)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "saved settings",
            "mode_label": "visible browser",
            "cdp_url": "",
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 9",
            "headless": False,
        },
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.get("/demo")
    assert resp.status_code == 200
    assert b"Launch Instant Demo Mode" in resp.data
    assert b"Run Gemini E2E Orchestrator" in resp.data
    assert b"Post Latest Reel" in resp.data
    assert b"Generate Video From Structure DB" in resp.data
    assert b"Engage Latest IG Comments" in resp.data
    assert b"Stop Pipeline Loop" in resp.data
    assert b"Cycles: 4" in resp.data
    assert b"Latest caption" in resp.data
    assert b"Replies logged: 2" in resp.data
    assert b"TechTok Sarah" in resp.data
    assert b"visible browser" in resp.data


def test_preview_page_renders_generated_video_gallery(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    def fake_get_json(api_base: str, path: str):
        if path == "/pipeline/runs?limit=24":
            return {
                "runs": [
                    {
                        "run_id": "run_dry",
                        "status": "ready",
                        "dry_run": True,
                        "product_title": "Dry Run Reel",
                        "product_description": "Latest dry-run placeholder.",
                        "caption": "caption dry",
                        "selected_template_id": "tpl_dry",
                        "video_path": str(tmp_path / "videos" / "dry.mp4"),
                        "avatar_image_path": None,
                        "product_image_path": None,
                        "updated_at": "2026-04-05T12:00:00Z",
                        "is_post_ready": True,
                    },
                    {
                        "run_id": "run_live",
                        "status": "posted",
                        "dry_run": False,
                        "product_title": "Live Reel",
                        "product_description": "Previous generated reel.",
                        "caption": "caption one",
                        "selected_template_id": "tpl_live",
                        "video_path": str(tmp_path / "videos" / "live.mp4"),
                        "avatar_image_path": None,
                        "product_image_path": None,
                        "updated_at": "2026-04-04T12:00:00Z",
                        "post_url": "https://instagram.com/p/demo",
                        "is_post_ready": True,
                    },
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(dashboard, "_get_json", fake_get_json)

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.get("/preview")
    assert resp.status_code == 200
    assert b"Generated Video Preview" in resp.data
    assert b"Dry Run Reel" in resp.data
    assert b"Live Reel" in resp.data
    assert b"caption one" in resp.data
    assert b"/artifacts/video?run_id=run_live" in resp.data
    assert b"Live" in resp.data
    assert b"Dry run" in resp.data


def test_preview_page_falls_back_to_local_videos_when_control_plane_is_offline(
    tmp_path, monkeypatch
) -> None:
    client = _build_client(tmp_path, monkeypatch)
    video_dir = tmp_path / "output" / "hackathon_videos"
    video_dir.mkdir(parents=True)
    sample_video = video_dir / "sample.mp4"
    sample_video.write_bytes(b"mp4")

    monkeypatch.setattr(
        dashboard,
        "_get_json",
        lambda api_base, path: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    monkeypatch.setattr(dashboard, "_ROOT", str(tmp_path / "runtime_dashboard"))

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.get("/preview")
    assert resp.status_code == 200
    assert b"Control plane history is offline" in resp.data
    assert b"sample" in resp.data
    assert b"hackathon_videos" in resp.data
    assert b"sample.mp4" in resp.data


def test_preview_page_falls_back_to_local_videos_when_control_plane_has_no_runs(
    tmp_path, monkeypatch
) -> None:
    client = _build_client(tmp_path, monkeypatch)
    video_dir = tmp_path / "output" / "hackathon_videos"
    video_dir.mkdir(parents=True)
    sample_video = video_dir / "sample.mp4"
    sample_video.write_bytes(b"mp4")

    def fake_get_json(api_base: str, path: str):
        assert path == "/pipeline/runs?limit=24"
        return {"runs": []}

    monkeypatch.setattr(dashboard, "_get_json", fake_get_json)
    monkeypatch.setattr(dashboard, "_ROOT", str(tmp_path / "runtime_dashboard"))

    with client.session_transaction() as sess:
        sess["use_fixture"] = False
        sess["api_base"] = "http://localhost:8000"

    resp = client.get("/preview")
    assert resp.status_code == 200
    assert b"sample" in resp.data
    assert b"sample.mp4" in resp.data
    assert b"Local file" in resp.data


def test_demo_run_pipeline_flashes_latest_run_summary(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    async def fake_wait_for_cdp(*args, **kwargs):
        return True

    def fake_post_json(api_base: str, path: str, payload: dict):
        assert path == "/pipeline/demo"
        assert payload["engagement_persona"]["instagram_handle"] == "@techtok.sarah"
        assert payload["dry_run"] is False
        assert payload["browser_runtime"]["cdp_url"] == "http://127.0.0.1:9222"
        return {
            "run": {
                "status": "ready",
                "reels_queued": 4,
                "structures_persisted": 4,
                "selected_template_id": "tpl_123",
            }
        }

    monkeypatch.setattr(dashboard, "_post_json", fake_post_json)
    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "environment",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "",
            "chrome_user_data_dir": "",
            "chrome_profile_directory": "",
            "headless": False,
        },
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/demo/run-pipeline", data={"run_mode": "live_visible"}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"Pipeline run finished." in resp.data
    assert b"live visible browser" in resp.data
    assert b"tpl_123" in resp.data


def test_demo_run_instant_demo_flashes_summary(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    async def fake_wait_for_cdp(*args, **kwargs):
        return True

    def fake_post_json(api_base: str, path: str, payload: dict):
        assert path == "/pipeline/demo-mode"
        assert payload["engagement_persona"]["instagram_handle"] == "@techtok.sarah"
        assert payload["dry_run"] is False
        assert payload["browser_runtime"]["cdp_url"] == "http://127.0.0.1:9222"
        return {
            "background_generation_started": True,
            "parallel_lanes": [
                "reel_discovery_to_video_structure",
                "video_structure_to_video_gen_and_instagram_posting",
                "comment_engagement",
            ],
        }

    monkeypatch.setattr(dashboard, "_post_json", fake_post_json)
    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "environment",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "",
            "chrome_user_data_dir": "",
            "chrome_profile_directory": "",
            "headless": False,
        },
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/demo/run-instant-demo", data={"run_mode": "live_visible"}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"Instant demo mode launched." in resp.data
    assert b"Parallel lanes: 3" in resp.data
    assert b"Background execution: started" in resp.data


def test_demo_engage_latest_flashes_summary(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    async def fake_wait_for_cdp(*args, **kwargs):
        return True

    def fake_post_json(api_base: str, path: str, payload: dict):
        assert path == "/pipeline/engage-latest"
        assert payload["browser_runtime"]["cdp_url"] == "http://127.0.0.1:9222"
        return {
            "engagement_summary": {
                "status": "replied",
                "total_replies_logged": 3,
            }
        }

    monkeypatch.setattr(dashboard, "_post_json", fake_post_json)
    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "environment",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "",
            "chrome_user_data_dir": "",
            "chrome_profile_directory": "",
            "headless": False,
        },
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post("/demo/engage-latest", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Latest post comment engagement finished." in resp.data
    assert b"Replies logged: 3" in resp.data


def test_demo_generate_video_flashes_summary(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    async def fake_wait_for_cdp(*args, **kwargs):
        return True

    def fake_post_json(api_base: str, path: str, payload: dict):
        assert path == "/pipeline/generate-video"
        assert payload["engagement_persona"]["instagram_handle"] == "@techtok.sarah"
        assert payload["dry_run"] is False
        assert payload["browser_runtime"]["cdp_url"] == "http://127.0.0.1:9222"
        return {
            "run": {
                "status": "ready",
                "selected_template_id": "tpl_db_123",
                "video_path": "/tmp/generated-db.mp4",
            }
        }

    monkeypatch.setattr(dashboard, "_post_json", fake_post_json)
    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "environment",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "",
            "chrome_user_data_dir": "",
            "chrome_profile_directory": "",
            "headless": False,
        },
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.post(
        "/demo/generate-video", data={"run_mode": "live_visible"}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"Generated a new video from the stored video structure database." in resp.data
    assert b"tpl_db_123" in resp.data


def test_build_engagement_persona_payload_prefers_active_instagram_identity() -> None:
    identities = load_identities(None)
    payload = dashboard._build_engagement_persona_payload(identities)

    assert payload["persona_name"] == "TechTok Sarah"
    assert payload["instagram_handle"] == "@techtok.sarah"


def test_settings_page_saves_browser_runtime_fields(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    resp = client.post(
        "/settings",
        data={
            "browser_use_api_key": "",
            "gemini": "",
            "twelvelabs": "",
            "browser_use_cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 9",
            "browser_use_headless": "false",
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Dashboard-triggered runs will use them immediately." in resp.data

    saved = secrets_store.read_raw()
    assert saved["BROWSER_USE_CDP_URL"] == "http://127.0.0.1:9222"
    assert saved["CHROME_EXECUTABLE_PATH"] == "/usr/bin/google-chrome"
    assert saved["CHROME_PROFILE_DIRECTORY"] == "Profile 9"
    assert saved["BROWSER_USE_HEADLESS"] == "false"


def test_settings_page_resolves_profile_name_and_detects_user_data_dir(
    tmp_path, monkeypatch
) -> None:
    client = _build_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dashboard,
        "detect_local_chrome_user_data_dir",
        lambda: "/home/kevin/.config/google-chrome",
    )
    monkeypatch.setattr(
        dashboard,
        "resolve_local_chrome_profile_directory",
        lambda profile_query, *, user_data_dir=None: "Profile 9",
    )

    resp = client.post(
        "/settings",
        data={
            "browser_use_api_key": "",
            "gemini": "",
            "twelvelabs": "",
            "browser_use_cdp_url": "",
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "",
            "chrome_profile_directory": "9",
            "browser_use_headless": "false",
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200
    saved = secrets_store.read_raw()
    assert os.path.normpath(saved["CHROME_USER_DATA_DIR"]) == os.path.normpath(
        "/home/kevin/.config/google-chrome"
    )
    assert saved["CHROME_PROFILE_DIRECTORY"] == "Profile 9"


def test_browser_runtime_state_prefers_saved_profile_over_stale_env(
    tmp_path, monkeypatch
) -> None:
    _build_client(tmp_path, monkeypatch)
    monkeypatch.setenv("CHROME_PROFILE_DIRECTORY", "Default")
    monkeypatch.setenv("CHROME_USER_DATA_DIR", "/env/user-data")
    monkeypatch.setattr(
        dashboard,
        "read_raw",
        lambda: {
            "CHROME_EXECUTABLE_PATH": "/usr/bin/google-chrome",
            "CHROME_USER_DATA_DIR": "/saved/user-data",
            "CHROME_PROFILE_DIRECTORY": "Profile 9",
            "BROWSER_USE_HEADLESS": "false",
        },
    )

    state = dashboard._browser_runtime_state()

    assert state["source"] == "saved settings"
    assert state["chrome_profile_directory"] == "Profile 9"
    assert state["chrome_user_data_dir"] == "/saved/user-data"


def test_launch_local_browser_saves_cdp_and_profile(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    clone_dir = tmp_path / "dashboard_clone"
    clone_calls: list[dict[str, object]] = []

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            return None

    async def fake_wait_for_cdp(*args, **kwargs):
        return False

    launched: dict[str, object] = {}

    def fake_ensure_profile_clone(**kwargs):
        clone_calls.append(kwargs)
        clone_dir.mkdir(parents=True, exist_ok=True)
        return clone_dir

    async def fake_launch_local_debug_chrome(**kwargs):
        launched.update(kwargs)
        return FakeProcess(), "http://127.0.0.1:9222"

    monkeypatch.setattr(dashboard, "ensure_profile_clone", fake_ensure_profile_clone)
    monkeypatch.setattr(dashboard, "profile_has_instagram_session", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(dashboard, "_runtime_clone_dir", lambda profile: clone_dir)
    monkeypatch.setattr(
        dashboard,
        "wait_for_cdp",
        fake_wait_for_cdp,
    )
    monkeypatch.setattr(
        dashboard,
        "launch_local_debug_chrome",
        fake_launch_local_debug_chrome,
    )

    resp = client.post(
        "/settings/launch-local-browser",
        data={
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 9",
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert clone_calls and clone_calls[0]["refresh"] is False
    assert os.path.normpath(str(launched["user_data_dir"])) == os.path.normpath(str(clone_dir))
    assert launched["profile_directory"] == "Profile 9"
    assert b"CDP is available at http://127.0.0.1:9222" in resp.data
    saved = secrets_store.read_raw()
    assert saved["BROWSER_USE_CDP_URL"] == "http://127.0.0.1:9222"
    assert saved["CHROME_PROFILE_DIRECTORY"] == "Profile 9"


def test_launch_local_browser_uses_new_port_when_existing_cdp_is_alive(
    tmp_path, monkeypatch
) -> None:
    client = _build_client(tmp_path, monkeypatch)
    launched: dict[str, object] = {}
    clone_dir = tmp_path / "dashboard_clone"
    clone_calls: list[dict[str, object]] = []

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            return None

    async def fake_wait_for_cdp(cdp_url: str, **kwargs):
        return cdp_url == "http://127.0.0.1:9222"

    def fake_ensure_profile_clone(**kwargs):
        clone_calls.append(kwargs)
        clone_dir.mkdir(parents=True, exist_ok=True)
        return clone_dir

    async def fake_launch_local_debug_chrome(**kwargs):
        launched.update(kwargs)
        return FakeProcess(), f"http://127.0.0.1:{kwargs['cdp_port']}"

    monkeypatch.setattr(dashboard, "ensure_profile_clone", fake_ensure_profile_clone)
    monkeypatch.setattr(dashboard, "profile_has_instagram_session", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(dashboard, "_runtime_clone_dir", lambda profile: clone_dir)
    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(dashboard, "launch_local_debug_chrome", fake_launch_local_debug_chrome)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "saved settings",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 3",
            "headless": False,
        },
    )

    resp = client.post(
        "/settings/launch-local-browser",
        data={
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 9",
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert launched["cdp_port"] == 9223
    assert clone_calls and clone_calls[0]["refresh"] is False
    assert os.path.normpath(str(launched["user_data_dir"])) == os.path.normpath(str(clone_dir))
    saved = secrets_store.read_raw()
    assert saved["BROWSER_USE_CDP_URL"] == "http://127.0.0.1:9223"
    assert saved["CHROME_PROFILE_DIRECTORY"] == "Profile 9"


def test_launch_local_browser_reuses_existing_managed_process_for_same_profile(
    tmp_path, monkeypatch
) -> None:
    client = _build_client(tmp_path, monkeypatch)
    app = client.application

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            raise AssertionError("existing managed browser should not be terminated")

    async def fake_wait_for_cdp(cdp_url: str, **kwargs):
        return cdp_url == "http://127.0.0.1:9222"

    async def fake_launch_local_debug_chrome(**kwargs):
        raise AssertionError("existing managed browser should not be relaunched")

    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(dashboard, "launch_local_debug_chrome", fake_launch_local_debug_chrome)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "saved settings",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 9",
            "headless": False,
        },
    )

    with app.app_context():
        app.extensions["local_debug_chrome_process"] = FakeProcess()

    resp = client.post(
        "/settings/launch-local-browser",
        data={
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 9",
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Reusing existing browser at http://127.0.0.1:9222" in resp.data
    saved = secrets_store.read_raw()
    assert saved["BROWSER_USE_CDP_URL"] == "http://127.0.0.1:9222"
    assert saved["CHROME_PROFILE_DIRECTORY"] == "Profile 9"


def test_browser_runtime_payload_falls_back_to_local_chrome_when_cdp_is_stale(
    tmp_path, monkeypatch
) -> None:
    async def fake_wait_for_cdp(*args, **kwargs):
        return False

    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    clone_dir = tmp_path / "dashboard_clone"
    clone_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dashboard, "_runtime_clone_dir", lambda profile: clone_dir)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "saved settings",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 3",
            "headless": False,
        },
    )

    payload = dashboard._browser_runtime_payload_for_control_plane()

    assert payload == {
        "use_cloud": False,
        "cloud_profile_id": None,
        "cloud_proxy_country_code": None,
        "local_profile_mode": "managed_runtime",
        "chrome_executable_path": "/usr/bin/google-chrome",
        "chrome_user_data_dir": str(clone_dir),
        "chrome_profile_directory": "Profile 3",
        "headless": False,
    }


def test_browser_runtime_payload_uses_dashboard_clone_dir_for_managed_browser(
    tmp_path, monkeypatch
) -> None:
    app = dashboard.create_app()
    app.config.update(TESTING=True)

    class FakeProcess:
        def poll(self):
            return None

    async def fake_wait_for_cdp(*args, **kwargs):
        return True

    monkeypatch.setattr(dashboard, "wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(
        dashboard,
        "_browser_runtime_state",
        lambda: {
            "ready": True,
            "source": "saved settings",
            "mode_label": "visible browser",
            "cdp_url": "http://127.0.0.1:9222",
            "chrome_executable_path": "/usr/bin/google-chrome",
            "chrome_user_data_dir": "/home/kevin/.config/google-chrome",
            "chrome_profile_directory": "Profile 9",
            "headless": False,
        },
    )
    clone_dir = tmp_path / "dashboard_clone"
    clone_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dashboard, "_runtime_clone_dir", lambda profile: clone_dir)
    with app.app_context():
        app.extensions["local_debug_chrome_process"] = FakeProcess()
        payload = dashboard._browser_runtime_payload_for_control_plane()

    assert payload == {
        "cdp_url": "http://127.0.0.1:9222",
        "use_cloud": False,
        "cloud_profile_id": None,
        "cloud_proxy_country_code": None,
        "local_profile_mode": "managed_runtime",
        "chrome_executable_path": "/usr/bin/google-chrome",
        "chrome_user_data_dir": str(clone_dir),
        "chrome_profile_directory": "Profile 9",
        "headless": False,
    }


def test_distribution_page_renders_engagement_history(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    monkeypatch.setattr(
        dashboard,
        "load_pipeline_posts",
        lambda base: [
            {
                "platform": "instagram",
                "status": "posted",
                "post_url": "https://www.instagram.com/reel/demo123/",
                "posted_at": "2026-04-05T12:00:00Z",
                "engagement_summary": {
                    "status": "replied",
                    "total_replies_logged": 2,
                    "last_run_at": "2026-04-05T12:05:00Z",
                    "recent_replies": [
                        {"commenter_handle": "fan1", "response_text": "thank you so much 🫶"}
                    ],
                },
                "recent_replies": [
                    {"commenter_handle": "fan1", "response_text": "thank you so much 🫶"}
                ],
                "engagement_reply_count": 2,
            }
        ],
    )

    with client.session_transaction() as sess:
        sess["use_fixture"] = False
        sess["api_base"] = "http://localhost:8000"

    resp = client.get("/distribution")
    assert resp.status_code == 200
    assert b"Engagement: REPLIED" in resp.data
    assert b"Replies logged: 2" in resp.data
    assert b"Recent replies" in resp.data


def test_analytics_page_renders_video_performance_placeholders(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    monkeypatch.setattr(
        dashboard,
        "_build_analytics_context",
        lambda api: {
            "analytics_summary_cards": [
                {"label": "Videos generated", "value": "3", "detail": "2 live-ready"},
                {"label": "Posts tracked", "value": "1", "detail": "Videos with a post URL"},
                {"label": "Analytics coverage", "value": "0", "detail": "Videos with real performance numbers"},
                {"label": "Comment replies", "value": "2", "detail": "Logged engagement actions"},
            ],
            "analytics_rows": [
                {
                    "product_title": "Explorerhd (400M)",
                    "run_id": "run_live_123",
                    "selected_template_id": "tpl_live",
                    "status": "posted",
                    "mode_label": "Live",
                    "posted_at": "2026-04-05T08:00:00Z",
                    "post_url": "https://www.instagram.com/reel/demo123/",
                    "metric_state": "Awaiting first analytics pull",
                    "views": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "saves": 0,
                    "engagement_status": "replied",
                    "engagement_reply_count": 2,
                }
            ],
            "latest_video_metrics": {
                "product_title": "Explorerhd (400M)",
                "run_id": "run_live_123",
                "status": "posted",
                "selected_template_id": "tpl_live",
                "updated_at": "2026-04-05T08:00:00Z",
                "post_url": "https://www.instagram.com/reel/demo123/",
            },
            "latest_video_snapshot": {
                "metric_state": "Awaiting first analytics pull",
                "views": 0,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "saves": 0,
                "reply_count": 2,
            },
            "analytics_control_plane_available": True,
        },
    )
    monkeypatch.setattr(dashboard, "load_optimization_directives", lambda api: [])
    monkeypatch.setattr(dashboard, "load_redo_queue", lambda api: [])

    with client.session_transaction() as sess:
        sess["use_fixture"] = False
        sess["api_base"] = "http://localhost:8000"

    resp = client.get("/analytics")
    assert resp.status_code == 200
    assert b"Recent Video Performance" in resp.data
    assert b"Awaiting first analytics pull" in resp.data
    assert b"Explorerhd (400M)" in resp.data
    assert b"Replies logged: 2" in resp.data


def test_database_page_renders_detected_databases(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    def fake_get_json(api_base: str, path: str):
        if path == "/pipeline/databases":
            return {
                "databases": [
                    {
                        "db_key": "state_db",
                        "filename": "abunnytech.db",
                        "role": "state_api",
                        "group": "state",
                        "path": "/tmp/abunnytech.db",
                        "tables": ["pipeline_records", "audit_logs"],
                        "size_bytes": 1024,
                        "exists": True,
                    }
                ]
            }
        assert path == "/pipeline/databases/state_db?page=1"
        return {
            "database": {
                "db_key": "state_db",
                "filename": "abunnytech.db",
                "role": "state_api",
                "group": "state",
                "path": "/tmp/abunnytech.db",
                "table_summaries": [{"name": "pipeline_records", "row_count": 2}],
                "selected_table": "pipeline_records",
                "preview": {
                    "table": "pipeline_records",
                    "page": 1,
                    "total_rows": 2,
                    "rows": [{"id": "abc"}],
                },
            }
        }

    monkeypatch.setattr(dashboard, "_get_json", fake_get_json)

    with client.session_transaction() as sess:
        sess["use_fixture"] = True
        sess["api_base"] = "http://localhost:8000"

    resp = client.get("/databases")
    assert resp.status_code == 200
    assert b"Database Explorer" in resp.data
    assert b"abunnytech.db" in resp.data
    assert b"pipeline_records" in resp.data
