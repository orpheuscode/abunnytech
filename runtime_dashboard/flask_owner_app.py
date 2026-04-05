"""
Flask owner dashboard for the abunnytech pipeline.

Run:
  uv run python -m runtime_dashboard.flask_owner_app

Or via demo launcher (``scripts/demo.py``).
"""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import httpx
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from runtime_dashboard.data_loader import (
    load_competitor_watchlist,
    load_content_packages,
    load_distribution_records,
    load_identities,
    load_optimization_directives,
    load_product_catalog,
    load_redo_queue,
    load_trending_audio,
    load_video_blueprints,
)
from runtime_dashboard.owner_data_store import create_fixture_product, update_fixture_identity_avatar
from runtime_dashboard.secrets_store import (
    ENV_BROWSER_USE_OPENAI,
    ENV_GEMINI_PRIMARY,
    ENV_TWELVE_PRIMARY,
    apply_to_environ,
    read_for_subprocess,
    read_raw,
    save_merged,
)

_ROOT = os.path.dirname(os.path.abspath(__file__))
_UPLOAD_DIR = Path(_ROOT) / "static" / "uploads"
_AVATAR_SUBDIR = "avatars"
_PRODUCT_SUBDIR = "products"
_ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

NAV_PAGES: list[tuple[str, str]] = [
    ("identity", "🧬 Identity"),
    ("discovery", "🔍 Discovery"),
    ("content", "🎬 Content"),
    ("distribution", "📦 Distribution"),
    ("analytics", "📊 Analytics"),
    ("catalog", "🛍️ Monetization"),
    ("demo", "🎮 Demo Control"),
    ("guided", "🎬 Guided Demo"),
]

PAGE_SLUGS = {p[0] for p in NAV_PAGES}

PIPELINE_STAGES: list[tuple[str, str, str, str]] = [
    ("Stage 0", "Identity", "#6c5ce7", "Define the AI persona"),
    ("Stage 1", "Discovery", "#00b894", "Discover trends & competitors"),
    ("Stage 2", "Content", "#fdcb6e", "Generate video blueprints & packages"),
    ("Stage 3", "Distribution", "#0984e3", "Distribute to platforms"),
    ("Stage 4", "Analytics", "#e17055", "Measure & optimize"),
    ("Stage 5", "Monetization", "#a29bfe", "Products & brand deals"),
]

GUIDED_TOTAL = 8


def _api_base() -> str | None:
    if session.get("use_fixture", True):
        return None
    base = (session.get("api_base") or "http://localhost:8000").strip().rstrip("/")
    return base or None


def _nav_context(active_slug: str) -> dict[str, Any]:
    session.setdefault("use_fixture", True)
    session.setdefault("api_base", "http://localhost:8000")
    return {
        "nav_pages": NAV_PAGES,
        "active_slug": active_slug,
        "use_fixture": session.get("use_fixture", True),
        "api_base": session.get("api_base", "http://localhost:8000"),
    }


def _redirect_back(default_slug: str) -> Any:
    nxt = request.form.get("next") or request.referrer or url_for("page", slug=default_slug)
    return redirect(nxt)


def _control_plane_base() -> str:
    configured = (os.environ.get("CONTROL_PLANE_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured

    api_base = (session.get("api_base") or "http://localhost:8000").strip().rstrip("/")
    parsed = urlparse(api_base)
    if not parsed.scheme or not parsed.netloc:
        return "http://localhost:8001"

    host = parsed.hostname or "localhost"
    port = parsed.port
    next_port = 8001 if port in (None, 8000) else port + 1
    netloc = f"{host}:{next_port}"
    return urlunparse((parsed.scheme, netloc, "", "", "", "")).rstrip("/")


def _save_uploaded_image(field_name: str, prefix: str, subdir: str = "") -> str:
    uploaded = request.files.get(field_name)
    if uploaded is None or not uploaded.filename:
        return ""

    original_name = secure_filename(uploaded.filename)
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_IMAGE_SUFFIXES:
        raise ValueError("Upload a PNG, JPG, GIF, or WEBP image.")

    target_dir = _UPLOAD_DIR / subdir if subdir else _UPLOAD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_name = f"{prefix}-{uuid4().hex}{suffix}"
    uploaded.save(target_dir / saved_name)
    url_path = f"uploads/{saved_name}" if not subdir else f"uploads/{subdir}/{saved_name}"
    return url_for("static", filename=url_path)


def _list_uploaded_assets(subdir: str) -> list[dict[str, str]]:
    target_dir = _UPLOAD_DIR / subdir
    if not target_dir.is_dir():
        return []

    assets: list[dict[str, str]] = []
    for path in sorted(target_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_file() or path.suffix.lower() not in _ALLOWED_IMAGE_SUFFIXES:
            continue
        assets.append(
            {
                "filename": path.name,
                "url": url_for("static", filename=f"uploads/{subdir}/{path.name}"),
                "path": str(path.resolve()),
            }
        )
    return assets


def _put_json(api_base: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = httpx.put(f"{api_base}{path}", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _post_json(api_base: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = httpx.post(f"{api_base}{path}", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_json(api_base: str, path: str) -> dict[str, Any]:
    resp = httpx.get(f"{api_base}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _parse_price_cents(raw_value: str) -> int:
    text = raw_value.strip()
    if not text:
        return 0
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Enter a valid product price.") from exc
    if amount < 0:
        raise ValueError("Price must be zero or greater.")
    normalized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((normalized * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _latest_uploaded_asset_path(subdir: str) -> str | None:
    target_dir = _UPLOAD_DIR / subdir
    if not target_dir.is_dir():
        return None

    candidates = [
        path for path in target_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _ALLOWED_IMAGE_SUFFIXES
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: item.stat().st_mtime)
    return str(latest.resolve())


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
    )
    app.secret_key = os.environ.get("OWNER_DASHBOARD_SECRET", "dev-insecure-change-me")

    apply_to_environ(read_for_subprocess())

    @app.route("/")
    def index() -> Any:
        return redirect(url_for("page", slug="identity"))

    @app.post("/prefs")
    def set_prefs() -> Any:
        session["use_fixture"] = request.form.get("use_fixture") == "1"
        session["api_base"] = (request.form.get("api_base") or "").strip() or "http://localhost:8000"
        nxt = request.form.get("next") or url_for("page", slug="identity")
        return redirect(nxt)

    @app.route("/settings", methods=["GET", "POST"])
    def settings() -> Any:
        if request.method == "POST":
            merged = save_merged(
                browser_use_openai=request.form.get("browser_use_openai", ""),
                gemini=request.form.get("gemini", ""),
                twelvelabs=request.form.get("twelvelabs", ""),
            )
            apply_to_environ(merged)
            flash("API keys saved. Restart demo services if they are already running.")
            return redirect(url_for("settings"))

        raw = read_raw()
        ctx = {
            **_nav_context("settings"),
            "page_title": "API keys",
            "saved_openai": ENV_BROWSER_USE_OPENAI in raw,
            "saved_gemini": ENV_GEMINI_PRIMARY in raw,
            "saved_twelve": ENV_TWELVE_PRIMARY in raw,
        }
        return render_template("owner/settings.html", **ctx)

    @app.route("/demo/dry-run", methods=["POST"])
    def demo_dry_run() -> Any:
        flash(
            "Dry-run complete (simulated). In a real run, all pipeline stages execute in demo mode."
        )
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/run-pipeline")
    def demo_run_pipeline() -> Any:
        payload = {
            "avatar_image_path": _latest_uploaded_asset_path(_AVATAR_SUBDIR),
            "product_image_path": _latest_uploaded_asset_path(_PRODUCT_SUBDIR),
        }
        try:
            result = _post_json(_control_plane_base(), "/pipeline/demo", payload)
            summary = result.get("summary", {})
            flash(
                "Entire pipeline run finished. "
                f"Templates: {summary.get('reel_summary', {}).get('templates_created', 0)}, "
                f"Videos: {summary.get('product_summary', {}).get('generations', 0)}, "
                f"Posts: {summary.get('publish_summary', {}).get('posts', 0)}."
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            flash(f"Could not run the full pipeline: {detail}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/run-gemini-orchestrator")
    def demo_run_gemini_orchestrator() -> Any:
        instruction = (
            request.form.get("instruction")
            or "Run the entire pipeline end to end for the shared Instagram storefront."
        ).strip()
        payload = {
            "instruction": instruction,
            "avatar_image_path": _latest_uploaded_asset_path(_AVATAR_SUBDIR),
            "product_image_path": _latest_uploaded_asset_path(_PRODUCT_SUBDIR),
        }
        try:
            result = _post_json(_control_plane_base(), "/pipeline/gemini-orchestrate", payload)
            final_text = result.get("final_text") or "Gemini orchestration completed."
            flash(final_text)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            flash(f"Could not run the Gemini orchestrator: {detail}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/start-loop")
    def demo_start_loop() -> Any:
        try:
            status = _post_json(_control_plane_base(), "/pipeline/loop/start", {})
            flash(
                "Pipeline loop started. "
                f"Interval: {status.get('interval_seconds', 'n/a')}s, "
                f"Cycles: {status.get('cycle_count', 0)}."
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            flash(f"Could not start the pipeline loop: {detail}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/stop-loop")
    def demo_stop_loop() -> Any:
        try:
            status = _post_json(_control_plane_base(), "/pipeline/loop/stop", {})
            flash(
                "Pipeline loop stopped. "
                f"Completed cycles: {status.get('cycle_count', 0)}."
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            flash(f"Could not stop the pipeline loop: {detail}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.route("/guided")
    def guided() -> Any:
        step = request.args.get("step", default=0, type=int)
        step = max(0, min(step, GUIDED_TOTAL - 1))
        ctx = {
            **_nav_context("guided"),
            "page_title": "Guided Demo",
            "step": step,
            "total": GUIDED_TOTAL,
            "stages": PIPELINE_STAGES,
        }
        return render_template("owner/guided.html", **ctx)

    @app.post("/avatars/upload")
    def upload_avatar_library_asset() -> Any:
        api = _api_base()

        try:
            avatar_url = _save_uploaded_image("avatar_file", "avatar", _AVATAR_SUBDIR)
            if not avatar_url:
                flash("Choose an avatar image to upload.")
                return _redirect_back("identity")

            # Keep the latest upload reflected in the first identity for current pipeline views,
            # while the full folder remains the source for future video generation.
            identities = load_identities(api)
            if identities:
                identity = identities[0]
                identity_id = str(identity.get("id", ""))
                avatar = identity.get("avatar")
                if not isinstance(avatar, dict):
                    avatar = {}
                avatar["avatar_url"] = avatar_url
                identity["avatar"] = avatar

                if api is None:
                    update_fixture_identity_avatar(identity_id, avatar_url)
                elif identity_id:
                    _put_json(api, f"/identity_matrix/{identity_id}", identity)

            flash("Avatar added to the library folder.")
        except ValueError as exc:
            flash(str(exc))
        except httpx.HTTPError as exc:
            flash(f"Could not save the avatar: {exc}")

        return _redirect_back("identity")

    @app.post("/catalog/products")
    def create_catalog_product() -> Any:
        api = _api_base()

        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Add a product name before saving.")
            return _redirect_back("catalog")
        if not description:
            flash("Add a product description before saving.")
            return _redirect_back("catalog")

        try:
            image_url = _save_uploaded_image("product_image", "product", _PRODUCT_SUBDIR)
            product = {
                "identity_id": None,
                "name": name,
                "description": description,
                "image_url": image_url,
                "price_cents": _parse_price_cents(request.form.get("price", "")),
                "url": (request.form.get("url") or "").strip(),
                "affiliate_code": (request.form.get("affiliate_code") or "").strip(),
                "active": request.form.get("active") == "1",
            }

            if api is None:
                create_fixture_product(product)
            else:
                _post_json(api, "/product_catalog", product)
            flash(f"Product saved: {name}")
        except ValueError as exc:
            flash(str(exc))
        except httpx.HTTPError as exc:
            flash(f"Could not save the product: {exc}")

        return _redirect_back("catalog")

    @app.route("/<slug>")
    def page(slug: str) -> Any:
        if slug not in PAGE_SLUGS:
            abort(404)

        api = _api_base()

        if slug == "identity":
            return render_template(
                "owner/identity.html",
                **_nav_context(slug),
                page_title="Identity",
                avatar_library=_list_uploaded_assets(_AVATAR_SUBDIR),
                avatar_library_path=str((_UPLOAD_DIR / _AVATAR_SUBDIR).resolve()),
                identities=load_identities(api),
            )

        if slug == "discovery":
            return render_template(
                "owner/discovery.html",
                **_nav_context(slug),
                page_title="Discovery",
                trending=load_trending_audio(api),
                competitors=load_competitor_watchlist(api),
            )

        if slug == "content":
            return render_template(
                "owner/content.html",
                **_nav_context(slug),
                page_title="Content",
                blueprints=load_video_blueprints(api),
                packages=load_content_packages(api),
            )

        if slug == "distribution":
            return render_template(
                "owner/distribution.html",
                **_nav_context(slug),
                page_title="Distribution",
                records=load_distribution_records(api),
            )

        if slug == "analytics":
            return render_template(
                "owner/analytics.html",
                **_nav_context(slug),
                page_title="Analytics",
                directives=load_optimization_directives(api),
                redo=load_redo_queue(api),
            )

        if slug == "catalog":
            return render_template(
                "owner/catalog.html",
                **_nav_context(slug),
                page_title="Monetization",
                products=load_product_catalog(api),
            )

        if slug == "demo":
            return _render_demo(api)

        abort(404)

    return app


def _render_demo(api: str | None) -> Any:
    identities = load_identities(api)
    trending = load_trending_audio(api)
    blueprints = load_video_blueprints(api)
    packages = load_content_packages(api)
    records = load_distribution_records(api)
    health = [
        ("Identities", len(identities)),
        ("Trending Audio", len(trending)),
        ("Blueprints", len(blueprints)),
        ("Content Packages", len(packages)),
        ("Distribution Records", len(records)),
    ]

    artifact_types: list[tuple[str, str]] = [
        ("identities", "Identity Matrix"),
        ("video_blueprints", "Video Blueprint"),
        ("content_packages", "Content Package"),
        ("distribution_records", "Distribution Record"),
        ("optimization_directives", "Optimization Directive"),
    ]
    loaders: dict[str, Any] = {
        "identities": load_identities,
        "video_blueprints": load_video_blueprints,
        "content_packages": load_content_packages,
        "distribution_records": load_distribution_records,
        "optimization_directives": load_optimization_directives,
    }

    artifact = request.args.get("artifact", "identities")
    if artifact not in loaders:
        artifact = "identities"
    data = loaders[artifact](api)
    idx = request.args.get("idx", default=0, type=int)
    if not data:
        selected_json = ""
        artifact_labels: list[tuple[int, str]] = []
    else:
        if isinstance(data, list):
            if idx < 0 or idx >= len(data):
                idx = 0
            labels: list[tuple[int, str]] = []
            for i, d in enumerate(data):
                if not isinstance(d, dict):
                    lab = str(i)
                else:
                    lab = str(
                        d.get("name")
                        or d.get("title")
                        or d.get("caption")
                        or (str(d.get("id", ""))[:8] or f"#{i}")
                    )
                labels.append((i, lab))
            artifact_labels = labels
            selected = data[idx]
        else:
            artifact_labels = []
            selected = data
        selected_json = json.dumps(selected, indent=2, default=str)

    directives = load_optimization_directives(api)
    latest_directive = directives[0] if directives else None
    redo = load_redo_queue(api)
    redo_pending = [r for r in redo if isinstance(r, dict) and not r.get("processed")]
    control_plane_base = _control_plane_base()
    try:
        loop_status = _get_json(control_plane_base, "/pipeline/loop/status")
        control_plane_available = True
    except httpx.HTTPError:
        loop_status = {
            "running": False,
            "configured": False,
            "cycle_count": 0,
            "last_started_at": None,
            "last_finished_at": None,
            "next_run_at": None,
            "last_error": "Control plane unavailable",
        }
        control_plane_available = False

    ctx = {
        **_nav_context("demo"),
        "page_title": "Demo Control",
        "health": health,
        "control_plane_base": control_plane_base,
        "control_plane_available": control_plane_available,
        "loop_status": loop_status,
        "artifact_types": artifact_types,
        "artifact": artifact,
        "artifact_records": data if isinstance(data, list) else [data],
        "artifact_labels": artifact_labels,
        "idx": idx,
        "selected_json": selected_json,
        "latest_directive": latest_directive,
        "redo_pending": redo_pending,
    }
    return render_template("owner/demo.html", **ctx)


app = create_app()


def main() -> None:
    port = int(os.environ.get("DASHBOARD_PORT", "8501"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1", use_reloader=False)


if __name__ == "__main__":
    main()
