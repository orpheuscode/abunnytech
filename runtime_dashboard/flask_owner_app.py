"""
Flask owner dashboard for the abunnytech pipeline.

Run:
  uv run python -m runtime_dashboard.flask_owner_app

Or via demo launcher (``scripts/demo.py``).
"""

from __future__ import annotations

import json
import os
from typing import Any

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

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

    ctx = {
        **_nav_context("demo"),
        "page_title": "Demo Control",
        "health": health,
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
