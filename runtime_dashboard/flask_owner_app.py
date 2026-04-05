"""
Flask owner dashboard for the abunnytech pipeline.

Run:
  uv run python -m runtime_dashboard.flask_owner_app

Or via demo launcher (``scripts/demo.py``).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import httpx
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    has_app_context,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from integration.local_instagram_browser import (
    ensure_profile_clone,
    launch_local_debug_chrome,
    wait_for_cdp,
)
from werkzeug.utils import secure_filename

from packages.shared.browser_runtime_config import (
    ENV_BROWSER_USE_CDP_URL,
    ENV_BROWSER_USE_HEADLESS,
    ENV_CHROME_EXECUTABLE_PATH,
    ENV_CHROME_PROFILE_DIRECTORY,
    ENV_CHROME_USER_DATA_DIR,
    build_effective_browser_runtime_env,
    detect_local_chrome_user_data_dir,
    has_browser_runtime_config,
    resolve_local_chrome_profile_directory,
)
from runtime_dashboard.data_loader import (
    filter_placeholder_items,
    load_competitor_watchlist,
    load_content_packages,
    load_distribution_records,
    load_identities,
    load_optimization_directives,
    load_pipeline_posts,
    load_product_catalog,
    load_redo_queue,
    load_trending_audio,
    load_video_blueprints,
)
from runtime_dashboard.owner_data_store import (
    create_fixture_product,
    delete_fixture_product,
    update_fixture_identity_avatar,
)
from runtime_dashboard.secrets_store import (
    ENV_BROWSER_USE_PRIMARY,
    ENV_GEMINI_PRIMARY,
    ENV_SELECTED_AVATAR_PATH,
    ENV_SELECTED_PRODUCT_KEY,
    ENV_TWELVE_PRIMARY,
    read_raw,
    save_raw_values,
    save_merged,
)

_ROOT = os.path.dirname(os.path.abspath(__file__))
_UPLOAD_DIR = Path(_ROOT) / "static" / "uploads"
_AVATAR_SUBDIR = "avatars"
_PRODUCT_SUBDIR = "products"
_ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_DASHBOARD_BROWSER_RUNTIME_DIR = Path(_ROOT).resolve().parent / "data" / "dashboard_chrome_runtime"
_DEFAULT_DASHBOARD_CDP_PORT = 9222

NAV_PAGES: list[tuple[str, str]] = [
    ("identity", "🧬 Identity"),
    ("discovery", "🔍 Discovery"),
    ("content", "🎬 Content"),
    ("distribution", "📦 Distribution"),
    ("analytics", "📊 Analytics"),
    ("catalog", "🛍️ Monetization"),
    ("preview", "🎞️ Preview"),
    ("demo", "🎮 Demo Control"),
    ("databases", "🗃️ Databases"),
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


def _service_alive(base_url: str, path: str = "/health") -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}{path}", timeout=0.75)
        response.raise_for_status()
    except httpx.HTTPError:
        return False
    return True


def _api_base() -> str | None:
    if session.get("use_fixture", True):
        return None
    base = (session.get("api_base") or "http://localhost:8000").strip().rstrip("/")
    return base or None


def _nav_context(active_slug: str) -> dict[str, Any]:
    if "api_base" not in session:
        session["api_base"] = "http://localhost:8000"
    if "use_fixture" not in session:
        session["use_fixture"] = not _service_alive(session["api_base"])
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
        path
        for path in target_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _ALLOWED_IMAGE_SUFFIXES
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: item.stat().st_mtime)
    return str(latest.resolve())


def _asset_path_from_static_url(url: str | None) -> str | None:
    text = str(url or "").strip()
    if not text.startswith("/static/"):
        return None
    relative = text.removeprefix("/static/").strip("/")
    path = Path(_ROOT).resolve() / "static" / relative
    return str(path.resolve()) if path.exists() else None


def _selected_avatar_path() -> str | None:
    selected = str(read_raw().get(ENV_SELECTED_AVATAR_PATH) or "").strip()
    if selected:
        candidate = Path(selected).expanduser().resolve()
        try:
            candidate.relative_to((_UPLOAD_DIR / _AVATAR_SUBDIR).resolve())
        except ValueError:
            candidate = None
        if candidate is not None and candidate.exists():
            return str(candidate)
    return _latest_uploaded_asset_path(_AVATAR_SUBDIR)


def _preferred_product(products: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not products:
        return None
    selected_key = str(read_raw().get(ENV_SELECTED_PRODUCT_KEY) or "").strip()
    if selected_key:
        for product in products:
            image_url = str(product.get("image_url") or "").strip()
            product_key = image_url or str(product.get("name") or "").strip()
            if product_key == selected_key:
                return product
    for product in products:
        if product.get("active"):
            return product
    return products[0]


def _latest_product_context(api: str | None) -> dict[str, str]:
    products = load_product_catalog(api)
    preferred = _preferred_product(products)
    if not preferred:
        return {"title": "", "description": ""}
    return {
        "title": str(preferred.get("name") or ""),
        "description": str(preferred.get("description") or ""),
    }


def _selected_product_image_path(api: str | None) -> str | None:
    preferred = _preferred_product(load_product_catalog(api))
    if preferred is not None:
        path = _asset_path_from_static_url(preferred.get("image_url"))
        if path:
            return path
    return _latest_uploaded_asset_path(_PRODUCT_SUBDIR)


def _default_engagement_persona_payload() -> dict[str, Any]:
    return {
        "persona_name": "abunnytech",
        "instagram_handle": "@abunnytech",
        "tone": "friendly",
        "sentence_length": "short",
        "emoji_usage": "1-2 per reply",
        "capitalization": "lowercase casual",
        "never_say": [],
        "response_examples": {
            "question": {
                "input": "where can i buy this?",
                "output": "check the link in bio and lmk if you have questions ✨",
            },
            "compliment": {
                "input": "love this",
                "output": "ahh thank you so much 🫶",
            },
        },
    }


def _browser_runtime_state() -> dict[str, Any]:
    raw = read_raw()
    dashboard_env = dict(os.environ)
    dashboard_env.update(raw)
    env_values = {
        key: str(os.environ.get(key) or "").strip()
        for key in (
            ENV_BROWSER_USE_CDP_URL,
            ENV_BROWSER_USE_HEADLESS,
            ENV_CHROME_EXECUTABLE_PATH,
            ENV_CHROME_USER_DATA_DIR,
            ENV_CHROME_PROFILE_DIRECTORY,
        )
        if str(os.environ.get(key) or "").strip()
    }
    saved_values = {
        key: str(raw.get(key) or "").strip()
        for key in (
            ENV_BROWSER_USE_CDP_URL,
            ENV_BROWSER_USE_HEADLESS,
            ENV_CHROME_EXECUTABLE_PATH,
            ENV_CHROME_USER_DATA_DIR,
            ENV_CHROME_PROFILE_DIRECTORY,
        )
        if str(raw.get(key) or "").strip()
    }
    saved_or_env = dict(saved_values)
    saved_or_env.update(
        {key: value for key, value in env_values.items() if key not in saved_or_env}
    )
    effective = build_effective_browser_runtime_env(saved=raw, environ=dashboard_env)

    if has_browser_runtime_config(saved_values):
        source = "saved settings"
    elif has_browser_runtime_config(env_values):
        source = "environment"
    elif has_browser_runtime_config(saved_or_env):
        source = "environment + saved settings"
    elif has_browser_runtime_config(effective):
        source = "auto-detected local Chrome"
    else:
        source = "missing"

    headless = str(effective.get(ENV_BROWSER_USE_HEADLESS, "false")).lower() == "true"
    return {
        "ready": has_browser_runtime_config(effective),
        "source": source,
        "mode_label": "headless" if headless else "visible browser",
        "cdp_url": effective.get(ENV_BROWSER_USE_CDP_URL) or "",
        "chrome_executable_path": effective.get(ENV_CHROME_EXECUTABLE_PATH) or "",
        "chrome_user_data_dir": effective.get(ENV_CHROME_USER_DATA_DIR) or "",
        "chrome_profile_directory": effective.get(ENV_CHROME_PROFILE_DIRECTORY) or "",
        "headless": headless,
    }


def _normalize_browser_runtime_form_data(form: Any) -> dict[str, str]:
    chrome_user_data_dir = str(form.get("chrome_user_data_dir", "") or "").strip()
    if not chrome_user_data_dir:
        chrome_user_data_dir = str(detect_local_chrome_user_data_dir() or "")

    chrome_profile_query = str(form.get("chrome_profile_directory", "") or "").strip()
    chrome_profile_directory = resolve_local_chrome_profile_directory(
        chrome_profile_query,
        user_data_dir=chrome_user_data_dir or None,
    )

    return {
        "browser_use_cdp_url": str(form.get("browser_use_cdp_url", "") or "").strip(),
        "chrome_executable_path": str(form.get("chrome_executable_path", "") or "").strip(),
        "chrome_user_data_dir": chrome_user_data_dir,
        "chrome_profile_directory": chrome_profile_directory or chrome_profile_query,
        "browser_use_headless": str(form.get("browser_use_headless", "") or "").strip(),
    }


def _browser_runtime_payload_for_control_plane() -> dict[str, Any] | None:
    browser_runtime = _browser_runtime_state()
    if not browser_runtime["ready"]:
        return None
    cdp_url = str(browser_runtime["cdp_url"] or "").strip()
    chrome_user_data_dir = str(browser_runtime["chrome_user_data_dir"] or "").strip()
    chrome_profile_directory = str(browser_runtime["chrome_profile_directory"] or "").strip()
    if chrome_profile_directory and has_app_context():
        managed_process = _current_local_debug_chrome_process(current_app)
        if managed_process is not None:
            clone_dir = _runtime_clone_dir(chrome_profile_directory)
            if clone_dir.is_dir():
                chrome_user_data_dir = str(clone_dir)
    chrome_payload_ready = bool(
        browser_runtime["chrome_executable_path"]
        and chrome_user_data_dir
        and chrome_profile_directory
    )
    if cdp_url:
        cdp_ok = False
        try:
            cdp_ok = asyncio.run(wait_for_cdp(cdp_url, timeout_seconds=1.0))
        except RuntimeError:
            cdp_ok = False
        if cdp_ok:
            return {
                "cdp_url": cdp_url,
                "chrome_executable_path": browser_runtime["chrome_executable_path"] or None,
                "chrome_user_data_dir": chrome_user_data_dir or None,
                "chrome_profile_directory": chrome_profile_directory or None,
                "headless": bool(browser_runtime["headless"]),
            }
        if chrome_payload_ready:
            return {
                "chrome_executable_path": browser_runtime["chrome_executable_path"],
                "chrome_user_data_dir": chrome_user_data_dir,
                "chrome_profile_directory": chrome_profile_directory,
                "headless": bool(browser_runtime["headless"]),
            }
    return {
        "cdp_url": None,
        "chrome_executable_path": browser_runtime["chrome_executable_path"] or None,
        "chrome_user_data_dir": chrome_user_data_dir or None,
        "chrome_profile_directory": chrome_profile_directory or None,
        "headless": bool(browser_runtime["headless"]),
    }


def _current_local_debug_chrome_process(app: Flask) -> subprocess.Popen[Any] | None:
    process = app.extensions.get("local_debug_chrome_process")
    if process is None:
        return None
    if process.poll() is not None:
        app.extensions["local_debug_chrome_process"] = None
        return None
    return process


def _runtime_clone_dir(profile_directory: str) -> Path:
    slug = profile_directory.strip().replace(os.sep, "_").replace(" ", "_") or "default"
    return _DASHBOARD_BROWSER_RUNTIME_DIR / slug


def _cdp_port_from_runtime_state(browser_runtime: dict[str, Any]) -> int:
    cdp_url = str(browser_runtime.get("cdp_url") or "").strip()
    if cdp_url:
        parsed = urlparse(cdp_url)
        if parsed.port:
            return parsed.port
    return _DEFAULT_DASHBOARD_CDP_PORT


def _next_available_cdp_port(start_port: int, *, attempts: int = 10) -> int:
    for offset in range(max(1, attempts)):
        candidate_port = start_port + offset
        candidate_url = f"http://127.0.0.1:{candidate_port}"
        try:
            if asyncio.run(wait_for_cdp(candidate_url, timeout_seconds=1.0)):
                continue
        except RuntimeError:
            pass
        return candidate_port
    return start_port + attempts


def _normalize_demo_run_mode(raw_value: str | None, *, browser_runtime_ready: bool) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"live", "live_visible", "visible"}:
        return "live_visible"
    if value == "dry_run":
        return "dry_run"
    return "live_visible" if browser_runtime_ready else "dry_run"


def _http_error_detail(exc: httpx.HTTPStatusError | httpx.HTTPError) -> str:
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response is None:
        return str(exc)
    try:
        payload = exc.response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    text = exc.response.text.strip()
    return text or str(exc)


def _build_engagement_persona_payload(identities: list[dict[str, Any]]) -> dict[str, Any]:
    for identity in identities:
        platforms = identity.get("platforms")
        if not isinstance(platforms, list):
            continue
        instagram = next(
            (
                platform
                for platform in platforms
                if isinstance(platform, dict)
                and str(platform.get("platform") or "").lower() == "instagram"
                and platform.get("active", True) is not False
            ),
            None,
        )
        if instagram is None:
            continue
        guidelines = (
            identity.get("guidelines") if isinstance(identity.get("guidelines"), dict) else {}
        )
        payload = _default_engagement_persona_payload()
        payload.update(
            {
                "source_identity_id": identity.get("id"),
                "persona_name": str(identity.get("name") or payload["persona_name"]),
                "instagram_handle": str(instagram.get("handle") or payload["instagram_handle"]),
                "tone": str(guidelines.get("tone") or payload["tone"]),
            }
        )
        return payload
    return _default_engagement_persona_payload()


def _normalize_distribution_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    engagement = normalized.get("engagement_summary")
    if not isinstance(engagement, dict):
        engagement = {
            "status": "not_run",
            "total_replies_logged": 0,
            "replies_posted_this_run": 0,
            "last_run_at": None,
            "last_reply_at": None,
            "last_reason": None,
            "last_error": None,
            "recent_replies": [],
        }
    recent_replies = normalized.get("recent_replies")
    if not isinstance(recent_replies, list):
        recent_replies = (
            engagement.get("recent_replies")
            if isinstance(engagement.get("recent_replies"), list)
            else []
        )
    normalized["engagement_summary"] = engagement
    normalized["recent_replies"] = recent_replies
    normalized["status"] = normalized.get("status") or (
        "posted" if normalized.get("post_url") else "pending"
    )
    normalized["dry_run"] = bool(normalized.get("dry_run", False))
    normalized["engagement_reply_count"] = int(
        normalized.get("engagement_reply_count")
        or engagement.get("total_replies_logged")
        or len(recent_replies)
    )
    normalized["error_message"] = (
        normalized.get("error_message") or engagement.get("last_error") or ""
    )
    return normalized


def _distribution_records_for_page(api: str | None) -> list[dict[str, Any]]:
    if api is None:
        return [
            _normalize_distribution_record(record) for record in load_distribution_records(None)
        ]

    control_plane_base = _control_plane_base()
    try:
        posts = load_pipeline_posts(control_plane_base)
        if posts:
            filtered_posts = filter_placeholder_items("distribution_records", posts)
            return [_normalize_distribution_record(record) for record in filtered_posts]
    except httpx.HTTPError:
        pass
    return [_normalize_distribution_record(record) for record in load_distribution_records(api)]


def _file_path_to_static_url(path_str: str | None) -> str | None:
    if not path_str:
        return None
    path = Path(path_str)
    try:
        relative = path.resolve().relative_to(Path(_ROOT).resolve() / "static")
    except ValueError:
        return None
    return url_for("static", filename=str(relative).replace(os.sep, "/"))


def _readiness_state() -> list[tuple[str, bool, str]]:
    raw = read_raw()
    browser_runtime = _browser_runtime_state()
    browser_ready = bool(
        raw.get(ENV_BROWSER_USE_PRIMARY) or os.environ.get(ENV_BROWSER_USE_PRIMARY)
    )
    gemini_ready = bool(raw.get(ENV_GEMINI_PRIMARY) or os.environ.get(ENV_GEMINI_PRIMARY))
    twelve_ready = bool(raw.get(ENV_TWELVE_PRIMARY) or os.environ.get(ENV_TWELVE_PRIMARY))
    if browser_runtime["cdp_url"]:
        chrome_detail = f"{browser_runtime['source']}: {browser_runtime['cdp_url']}"
    elif browser_runtime["ready"]:
        chrome_detail = (
            f"{browser_runtime['source']}: "
            f"{browser_runtime['chrome_executable_path']} "
            f"[{browser_runtime['chrome_profile_directory']}]"
        )
    else:
        chrome_detail = "BROWSER_USE_CDP_URL or CHROME_*"
    return [
        ("Browser Use API key", browser_ready, "BROWSER_USE_API_KEY"),
        ("Gemini API key", gemini_ready, "GOOGLE_API_KEY"),
        ("TwelveLabs API key", twelve_ready, "TWELVE_LABS_API_KEY"),
        ("Chrome/CDP config", bool(browser_runtime["ready"]), chrome_detail),
    ]


def _preview_record_from_run(run: dict[str, Any]) -> dict[str, Any]:
    video_path = str(run.get("video_path") or "").strip()
    run_id = str(run.get("run_id") or "").strip()
    video_url = None
    if run_id and video_path:
        video_url = url_for("artifact_video", run_id=run_id)
    dry_run = bool(run.get("dry_run", False))
    status = str(run.get("status") or "unknown").strip()
    mode_label = "Dry run" if dry_run else "Live"
    sort_priority = 0 if (not dry_run and status in {"ready", "posted"}) else 1 if not dry_run else 2
    return {
        **run,
        "preview_id": run_id or video_path,
        "source": "pipeline_run",
        "video_url": video_url,
        "poster_url": _file_path_to_static_url(run.get("product_image_path")),
        "avatar_url": _file_path_to_static_url(run.get("avatar_image_path")),
        "mode_label": mode_label,
        "sort_priority": sort_priority,
    }


def _preview_record_from_file(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "preview_id": str(path),
        "source": "local_file",
        "run_id": None,
        "status": "local_file",
        "dry_run": None,
        "video_path": str(path),
        "video_url": url_for("artifact_video", path=str(path)),
        "product_title": path.stem.replace("_", " "),
        "product_description": "Local generated video artifact",
        "caption": "",
        "selected_template_id": None,
        "post_url": None,
        "created_at": None,
        "updated_at": None,
        "finished_at": None,
        "filesize_bytes": stat.st_size,
        "mode_label": "Local file",
        "sort_priority": 3,
    }


def _fallback_preview_records(limit: int = 24) -> list[dict[str, Any]]:
    repo_root = Path(_ROOT).resolve().parent
    video_dir = repo_root / "output" / "hackathon_videos"
    if not video_dir.is_dir():
        return []
    candidates = sorted(
        (path for path in video_dir.glob("*.mp4") if path.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return [_preview_record_from_file(path.resolve()) for path in candidates[:limit]]


def _load_preview_records(*, limit: int = 24) -> tuple[list[dict[str, Any]], bool]:
    control_plane_base = _control_plane_base()
    try:
        response = _get_json(control_plane_base, f"/pipeline/runs?limit={limit}")
        runs = response.get("runs") or []
        records = [
            _preview_record_from_run(run)
            for run in runs
            if isinstance(run, dict) and str(run.get("video_path") or "").strip()
        ]
        records.sort(
            key=lambda record: str(record.get("updated_at") or record.get("finished_at") or ""),
            reverse=True,
        )
        records.sort(key=lambda record: int(record.get("sort_priority", 99)))
        return records, True
    except httpx.HTTPError:
        return _fallback_preview_records(limit), False


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _analytics_metric_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    views = _as_int(item.get("views"))
    likes = _as_int(item.get("likes"))
    comments = _as_int(item.get("comments"))
    shares = _as_int(item.get("shares"))
    saves = _as_int(item.get("saves"))
    has_real_metrics = any(value > 0 for value in (views, likes, comments, shares, saves))
    engagement_summary = (
        item.get("engagement_summary") if isinstance(item.get("engagement_summary"), dict) else {}
    )
    return {
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "saves": saves,
        "reply_count": _as_int(
            item.get("engagement_reply_count") or engagement_summary.get("total_replies_logged")
        ),
        "engagement_status": str(engagement_summary.get("status") or "not_run"),
        "has_real_metrics": has_real_metrics,
        "metric_state": "Live metrics" if has_real_metrics else "Awaiting first analytics pull",
    }


def _build_analytics_context(api: str | None) -> dict[str, Any]:
    preview_records, control_plane_available = _load_preview_records(limit=12)
    distribution_records = _distribution_records_for_page(api)
    posts_by_url = {
        str(record.get("post_url") or "").strip(): record
        for record in distribution_records
        if isinstance(record, dict) and str(record.get("post_url") or "").strip()
    }

    rows: list[dict[str, Any]] = []
    for record in preview_records:
        if not isinstance(record, dict):
            continue
        post = posts_by_url.get(str(record.get("post_url") or "").strip(), {})
        metric_source = post if post else record
        metrics = _analytics_metric_snapshot(metric_source)
        rows.append(
            {
                **record,
                "posted_at": post.get("posted_at") or record.get("finished_at") or record.get("updated_at"),
                "engagement_summary": post.get("engagement_summary") or record.get("engagement_summary") or {},
                "engagement_reply_count": metrics["reply_count"],
                "views": metrics["views"],
                "likes": metrics["likes"],
                "comments": metrics["comments"],
                "shares": metrics["shares"],
                "saves": metrics["saves"],
                "engagement_status": metrics["engagement_status"],
                "has_real_metrics": metrics["has_real_metrics"],
                "metric_state": metrics["metric_state"],
            }
        )

    live_rows = [row for row in rows if row.get("source") == "pipeline_run" and not row.get("dry_run")]
    posted_rows = [row for row in rows if row.get("post_url")]
    real_metric_rows = [row for row in rows if row.get("has_real_metrics")]
    latest_video = posted_rows[0] if posted_rows else live_rows[0] if live_rows else rows[0] if rows else None

    snapshot = (
        _analytics_metric_snapshot(latest_video)
        if isinstance(latest_video, dict)
        else _analytics_metric_snapshot({})
    )
    summary_cards = [
        {
            "label": "Videos generated",
            "value": str(len(rows)),
            "detail": f"{len(live_rows)} live-ready",
        },
        {
            "label": "Posts tracked",
            "value": str(len(posted_rows)),
            "detail": "Videos with a post URL",
        },
        {
            "label": "Analytics coverage",
            "value": str(len(real_metric_rows)),
            "detail": "Videos with real performance numbers",
        },
        {
            "label": "Comment replies",
            "value": str(sum(_as_int(row.get('engagement_reply_count')) for row in rows)),
            "detail": "Logged engagement actions",
        },
    ]
    return {
        "analytics_summary_cards": summary_cards,
        "analytics_rows": rows[:8],
        "latest_video_metrics": latest_video,
        "latest_video_snapshot": snapshot,
        "analytics_control_plane_available": control_plane_available,
    }


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
    )
    app.secret_key = os.environ.get("OWNER_DASHBOARD_SECRET", "dev-insecure-change-me")
    app.extensions["local_debug_chrome_process"] = None

    @app.route("/")
    def index() -> Any:
        return redirect(url_for("page", slug="identity"))

    @app.post("/prefs")
    def set_prefs() -> Any:
        session["use_fixture"] = request.form.get("use_fixture") == "1"
        session["api_base"] = (
            request.form.get("api_base") or ""
        ).strip() or "http://localhost:8000"
        nxt = request.form.get("next") or url_for("page", slug="identity")
        return redirect(nxt)

    @app.route("/settings", methods=["GET", "POST"])
    def settings() -> Any:
        if request.method == "POST":
            runtime_fields = _normalize_browser_runtime_form_data(request.form)
            save_merged(
                browser_use_api_key=request.form.get("browser_use_api_key", ""),
                gemini=request.form.get("gemini", ""),
                twelvelabs=request.form.get("twelvelabs", ""),
                **runtime_fields,
            )
            flash("Runtime settings saved. Dashboard-triggered runs will use them immediately.")
            return redirect(url_for("settings"))

        raw = read_raw()
        browser_runtime = _browser_runtime_state()
        ctx = {
            **_nav_context("settings"),
            "page_title": "Runtime setup",
            "saved_browser_use": ENV_BROWSER_USE_PRIMARY in raw,
            "saved_gemini": ENV_GEMINI_PRIMARY in raw,
            "saved_twelve": ENV_TWELVE_PRIMARY in raw,
            "saved_browser_runtime": any(
                key in raw
                for key in (
                    ENV_BROWSER_USE_CDP_URL,
                    ENV_BROWSER_USE_HEADLESS,
                    ENV_CHROME_EXECUTABLE_PATH,
                    ENV_CHROME_USER_DATA_DIR,
                    ENV_CHROME_PROFILE_DIRECTORY,
                )
            ),
            "browser_use_cdp_url": browser_runtime["cdp_url"],
            "chrome_executable_path": browser_runtime["chrome_executable_path"],
            "chrome_user_data_dir": browser_runtime["chrome_user_data_dir"],
            "chrome_profile_directory": browser_runtime["chrome_profile_directory"],
            "browser_use_headless": "true" if browser_runtime["headless"] else "false",
            "browser_runtime_source": browser_runtime["source"],
            "browser_runtime_mode_label": browser_runtime["mode_label"],
        }
        return render_template("owner/settings.html", **ctx)

    @app.post("/settings/launch-local-browser")
    def launch_local_browser() -> Any:
        runtime_fields = _normalize_browser_runtime_form_data(request.form)
        chrome_path = (
            runtime_fields["chrome_executable_path"]
            or _browser_runtime_state()["chrome_executable_path"]
        )
        chrome_user_data_dir = runtime_fields["chrome_user_data_dir"]
        chrome_profile_directory = runtime_fields["chrome_profile_directory"]

        if not chrome_path:
            flash("Chrome executable path is missing. Save runtime setup first.")
            return redirect(url_for("settings"))
        if not chrome_user_data_dir:
            flash("Chrome user data dir could not be detected. Set it in Runtime Setup.")
            return redirect(url_for("settings"))
        if not chrome_profile_directory:
            flash("Chrome profile could not be resolved. Type a profile name such as 'Profile 9'.")
            return redirect(url_for("settings"))

        browser_runtime = _browser_runtime_state()
        preferred_port = _cdp_port_from_runtime_state(browser_runtime)
        managed_process = _current_local_debug_chrome_process(app)
        if managed_process is not None:
            managed_process.terminate()
            app.extensions["local_debug_chrome_process"] = None
            cdp_port = preferred_port
        else:
            cdp_port = _next_available_cdp_port(preferred_port)

        try:
            ensure_profile_clone(
                source_user_data_dir=chrome_user_data_dir,
                profile_directory=chrome_profile_directory,
                target_user_data_dir=_runtime_clone_dir(chrome_profile_directory),
                refresh=True,
            )
            process, launched_cdp_url = asyncio.run(
                launch_local_debug_chrome(
                    cdp_port=cdp_port,
                    user_data_dir=_runtime_clone_dir(chrome_profile_directory),
                    profile_directory=chrome_profile_directory,
                    chrome_path=chrome_path,
                    start_url="https://www.instagram.com/",
                )
            )
        except FileNotFoundError as exc:
            flash(f"Could not launch Chrome: {exc}")
            return redirect(url_for("settings"))
        except RuntimeError as exc:
            flash(f"Could not launch Chrome: {exc}")
            return redirect(url_for("settings"))

        app.extensions["local_debug_chrome_process"] = process

        save_merged(
            browser_use_api_key="",
            gemini="",
            twelvelabs="",
            browser_use_cdp_url=launched_cdp_url,
            chrome_executable_path=chrome_path,
            chrome_user_data_dir=chrome_user_data_dir,
            chrome_profile_directory=chrome_profile_directory,
            browser_use_headless="false",
        )
        flash(
            f"Launched Chrome for {chrome_profile_directory}. "
            f"CDP is available at {launched_cdp_url}."
        )
        return redirect(url_for("settings"))

    @app.route("/demo/dry-run", methods=["POST"])
    def demo_dry_run() -> Any:
        flash(
            "Dry-run complete (simulated). In a real run, all pipeline stages execute in demo mode."
        )
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/run-pipeline")
    def demo_run_pipeline() -> Any:
        api = _api_base()
        product_context = _latest_product_context(api)
        identities = load_identities(api)
        browser_runtime = _browser_runtime_state()
        run_mode = _normalize_demo_run_mode(
            request.form.get("run_mode"),
            browser_runtime_ready=bool(browser_runtime["ready"]),
        )
        session["demo_run_mode"] = run_mode
        payload = {
            "dry_run": run_mode != "live_visible",
            "avatar_image_path": _selected_avatar_path(),
            "product_image_path": _selected_product_image_path(api),
            "product_title": product_context["title"],
            "product_description": product_context["description"],
            "engagement_persona": _build_engagement_persona_payload(identities),
            "browser_runtime": _browser_runtime_payload_for_control_plane(),
        }
        try:
            result = _post_json(_control_plane_base(), "/pipeline/demo", payload)
            run = result.get("run") or {}
            if run.get("status") == "failed":
                flash(f"Pipeline run failed: {run.get('error', 'unknown error')}")
            else:
                flash(
                    "Pipeline run finished. "
                    f"Mode: {'live visible browser' if run_mode == 'live_visible' else 'dry run'}. "
                    f"Queued reels: {run.get('reels_queued', 0)}, "
                    f"Structures: {run.get('structures_persisted', 0)}, "
                    f"Template: {run.get('selected_template_id') or 'n/a'}."
                )
        except httpx.HTTPStatusError as exc:
            flash(f"Could not run the full pipeline: {_http_error_detail(exc)}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/run-instant-demo")
    def demo_run_instant_demo() -> Any:
        api = _api_base()
        product_context = _latest_product_context(api)
        identities = load_identities(api)
        browser_runtime = _browser_runtime_state()
        run_mode = _normalize_demo_run_mode(
            request.form.get("run_mode"),
            browser_runtime_ready=bool(browser_runtime["ready"]),
        )
        session["demo_run_mode"] = run_mode
        payload = {
            "dry_run": run_mode != "live_visible",
            "avatar_image_path": _selected_avatar_path(),
            "product_image_path": _selected_product_image_path(api),
            "product_title": product_context["title"],
            "product_description": product_context["description"],
            "engagement_persona": _build_engagement_persona_payload(identities),
            "browser_runtime": _browser_runtime_payload_for_control_plane(),
        }
        try:
            result = _post_json(_control_plane_base(), "/pipeline/demo-mode", payload)
            lanes = result.get("parallel_lanes") or []
            flash(
                "Instant demo mode launched. "
                f"Parallel lanes: {len(lanes)}. "
                f"Background execution: {'started' if result.get('background_generation_started') else 'not started'}."
            )
        except httpx.HTTPStatusError as exc:
            flash(f"Could not launch instant demo mode: {_http_error_detail(exc)}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/engage-latest")
    def demo_engage_latest() -> Any:
        try:
            result = _post_json(
                _control_plane_base(),
                "/pipeline/engage-latest",
                {
                    "dry_run": False,
                    "browser_runtime": _browser_runtime_payload_for_control_plane(),
                },
            )
            summary = result.get("engagement_summary") or {}
            flash(
                "Latest post comment engagement finished. "
                f"Status: {summary.get('status') or 'unknown'}, "
                f"Replies logged: {summary.get('total_replies_logged', 0)}."
            )
        except httpx.HTTPStatusError as exc:
            flash(f"Could not engage the latest post comments: {_http_error_detail(exc)}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/post-latest")
    def demo_post_latest() -> Any:
        try:
            result = _post_json(
                _control_plane_base(),
                "/pipeline/post-latest",
                {
                    "dry_run": False,
                    "browser_runtime": _browser_runtime_payload_for_control_plane(),
                },
            )
            run = result.get("run") or {}
            flash(f"Latest generated run was posted. Post URL: {run.get('post_url') or 'n/a'}")
        except httpx.HTTPStatusError as exc:
            flash(f"Could not post the latest run: {_http_error_detail(exc)}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/generate-video")
    def demo_generate_video() -> Any:
        api = _api_base()
        product_context = _latest_product_context(api)
        identities = load_identities(api)
        browser_runtime = _browser_runtime_state()
        run_mode = _normalize_demo_run_mode(
            request.form.get("run_mode"),
            browser_runtime_ready=bool(browser_runtime["ready"]),
        )
        session["demo_run_mode"] = run_mode
        payload = {
            "dry_run": run_mode != "live_visible",
            "avatar_image_path": _selected_avatar_path(),
            "product_image_path": _selected_product_image_path(api),
            "product_title": product_context["title"],
            "product_description": product_context["description"],
            "engagement_persona": _build_engagement_persona_payload(identities),
            "browser_runtime": _browser_runtime_payload_for_control_plane(),
        }
        try:
            result = _post_json(_control_plane_base(), "/pipeline/generate-video", payload)
            run = result.get("run") or {}
            if run.get("status") == "failed":
                flash(f"DB-backed video generation failed: {run.get('error', 'unknown error')}")
            else:
                flash(
                    "Generated a new video from the stored video structure database. "
                    f"Template: {run.get('selected_template_id') or 'n/a'}, "
                    f"Video: {run.get('video_path') or 'n/a'}."
                )
        except httpx.HTTPStatusError as exc:
            flash(f"Could not generate video from the structure DB: {_http_error_detail(exc)}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/run-gemini-orchestrator")
    def demo_run_gemini_orchestrator() -> Any:
        instruction = (
            request.form.get("instruction")
            or (
                "Run the full storefront pipeline end to end: discover winning reels, build templates, "
                "pick the best product, generate the video, publish it, engage comments when live, "
                "and feed analytics back into the template store."
            )
        ).strip()
        browser_runtime = _browser_runtime_state()
        run_mode = _normalize_demo_run_mode(
            request.form.get("run_mode"),
            browser_runtime_ready=bool(browser_runtime["ready"]),
        )
        session["demo_run_mode"] = run_mode
        product_context = _latest_product_context(_api_base())
        payload = {
            "instruction": instruction,
            "dry_run": run_mode != "live_visible",
            "avatar_image_path": _selected_avatar_path(),
            "product_image_path": _selected_product_image_path(_api_base()),
            "product_title": product_context["title"],
            "product_description": product_context["description"],
            "browser_runtime": _browser_runtime_payload_for_control_plane(),
        }
        try:
            result = _post_json(_control_plane_base(), "/pipeline/gemini-orchestrate", payload)
            final_text = result.get("final_text") or "Gemini orchestration completed."
            flash(final_text)
        except httpx.HTTPStatusError as exc:
            flash(f"Could not run the Gemini orchestrator: {_http_error_detail(exc)}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/start-loop")
    def demo_start_loop() -> Any:
        browser_runtime = _browser_runtime_state()
        run_mode = _normalize_demo_run_mode(
            request.form.get("run_mode"),
            browser_runtime_ready=bool(browser_runtime["ready"]),
        )
        session["demo_run_mode"] = run_mode
        try:
            status = _post_json(
                _control_plane_base(),
                "/pipeline/loop/start",
                {
                    "dry_run": run_mode != "live_visible",
                    "browser_runtime": _browser_runtime_payload_for_control_plane(),
                },
            )
            flash(
                "Pipeline loop started. "
                f"Mode: {'live visible browser' if run_mode == 'live_visible' else 'dry run'}. "
                f"Interval: {status.get('interval_seconds', 'n/a')}s, "
                f"Cycles: {status.get('cycle_count', 0)}."
            )
        except httpx.HTTPStatusError as exc:
            flash(f"Could not start the pipeline loop: {_http_error_detail(exc)}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.post("/demo/stop-loop")
    def demo_stop_loop() -> Any:
        try:
            status = _post_json(_control_plane_base(), "/pipeline/loop/stop", {})
            flash(f"Pipeline loop stopped. Completed cycles: {status.get('cycle_count', 0)}.")
        except httpx.HTTPStatusError as exc:
            flash(f"Could not stop the pipeline loop: {_http_error_detail(exc)}")
        except httpx.HTTPError as exc:
            flash(f"Could not reach the control plane: {exc}")
        return redirect(url_for("page", slug="demo"))

    @app.get("/artifacts/video")
    def artifact_video() -> Any:
        run_id = (request.args.get("run_id") or "").strip()
        path_value = (request.args.get("path") or "").strip()
        resolved_path: Path | None = None

        if run_id:
            result = _get_json(_control_plane_base(), f"/pipeline/runs/{run_id}")
            run = result.get("run") or {}
            path_value = str(run.get("video_path") or "")

        if path_value:
            candidate = Path(path_value).expanduser().resolve()
            repo_root = Path(_ROOT).resolve().parent
            if candidate.suffix.lower() != ".mp4":
                abort(404)
            try:
                candidate.relative_to(repo_root)
            except ValueError:
                abort(403)
            if not candidate.exists():
                abort(404)
            resolved_path = candidate

        if resolved_path is None:
            abort(404)
        return send_file(resolved_path, mimetype="video/mp4", conditional=True)

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

    @app.post("/avatars/select")
    def select_avatar_library_asset() -> Any:
        asset_path = str(request.form.get("asset_path") or "").strip()
        candidate = Path(asset_path).expanduser().resolve()
        try:
            candidate.relative_to((_UPLOAD_DIR / _AVATAR_SUBDIR).resolve())
        except ValueError:
            flash("Avatar selection must come from the saved avatar folder.")
            return _redirect_back("identity")
        if not candidate.exists():
            flash("Selected avatar file no longer exists.")
            return _redirect_back("identity")
        save_raw_values({ENV_SELECTED_AVATAR_PATH: str(candidate)})
        flash(f"Avatar selected for generation: {candidate.name}")
        return _redirect_back("identity")

    @app.post("/avatars/delete")
    def delete_avatar_library_asset() -> Any:
        asset_path = str(request.form.get("asset_path") or "").strip()
        candidate = Path(asset_path).expanduser().resolve()
        try:
            candidate.relative_to((_UPLOAD_DIR / _AVATAR_SUBDIR).resolve())
        except ValueError:
            flash("Avatar deletion is limited to saved avatar uploads.")
            return _redirect_back("identity")
        if candidate.exists():
            candidate.unlink()
        selected = str(read_raw().get(ENV_SELECTED_AVATAR_PATH) or "").strip()
        if selected and Path(selected).expanduser().resolve() == candidate:
            save_raw_values({ENV_SELECTED_AVATAR_PATH: None})
        flash(f"Avatar removed: {candidate.name}")
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

    @app.post("/catalog/products/select")
    def select_catalog_product() -> Any:
        product_key = str(request.form.get("product_key") or "").strip()
        if not product_key:
            flash("Choose a product to use for generation.")
            return _redirect_back("catalog")
        save_raw_values({ENV_SELECTED_PRODUCT_KEY: product_key})
        flash("Selected storefront product for generation.")
        return _redirect_back("catalog")

    @app.post("/catalog/products/delete")
    def delete_catalog_product() -> Any:
        api = _api_base()
        name = str(request.form.get("name") or "").strip()
        image_url = str(request.form.get("image_url") or "").strip()
        if not name:
            flash("Could not identify the product to delete.")
            return _redirect_back("catalog")

        if api is None:
            removed = delete_fixture_product(name=name, image_url=image_url)
            if removed is None:
                flash("Product was not found in the storefront list.")
                return _redirect_back("catalog")
        else:
            flash("Product deletion is only wired for fixture mode right now.")
            return _redirect_back("catalog")

        image_path = _asset_path_from_static_url(image_url)
        if image_path:
            candidate = Path(image_path)
            if candidate.exists():
                candidate.unlink()
        selected_key = str(read_raw().get(ENV_SELECTED_PRODUCT_KEY) or "").strip()
        if selected_key and selected_key == (image_url or name):
            save_raw_values({ENV_SELECTED_PRODUCT_KEY: None})
        flash(f"Product removed: {name}")
        return _redirect_back("catalog")

    @app.route("/<slug>")
    def page(slug: str) -> Any:
        if slug not in PAGE_SLUGS:
            abort(404)

        api = _api_base()

        if slug == "identity":
            avatar_library = _list_uploaded_assets(_AVATAR_SUBDIR)
            selected_avatar_path = str(read_raw().get(ENV_SELECTED_AVATAR_PATH) or "").strip()
            for asset in avatar_library:
                asset["selected"] = asset.get("path") == selected_avatar_path
            return render_template(
                "owner/identity.html",
                **_nav_context(slug),
                page_title="Identity",
                avatar_library=avatar_library,
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
                records=_distribution_records_for_page(api),
            )

        if slug == "analytics":
            analytics = _build_analytics_context(api)
            return render_template(
                "owner/analytics.html",
                **_nav_context(slug),
                page_title="Analytics",
                directives=load_optimization_directives(api),
                redo=load_redo_queue(api),
                **analytics,
            )

        if slug == "catalog":
            products = load_product_catalog(api)
            selected_key = str(read_raw().get(ENV_SELECTED_PRODUCT_KEY) or "").strip()
            preferred = _preferred_product(products)
            preferred_key = ""
            if preferred is not None:
                preferred_key = str(preferred.get("image_url") or preferred.get("name") or "").strip()
            for product in products:
                product_key = str(product.get("image_url") or product.get("name") or "").strip()
                product["product_key"] = product_key
                product["selected"] = product_key == (selected_key or preferred_key)
            return render_template(
                "owner/catalog.html",
                **_nav_context(slug),
                page_title="Monetization",
                products=products,
            )

        if slug == "preview":
            return _render_preview(api)

        if slug == "demo":
            return _render_demo(api)

        if slug == "databases":
            return _render_databases()

        abort(404)

    return app


def _render_demo(api: str | None) -> Any:
    identities = load_identities(api)
    products = load_product_catalog(api)
    trending = load_trending_audio(api)
    blueprints = load_video_blueprints(api)
    packages = load_content_packages(api)
    records = _distribution_records_for_page(api)
    browser_runtime = _browser_runtime_state()
    demo_run_mode = _normalize_demo_run_mode(
        session.get("demo_run_mode"),
        browser_runtime_ready=bool(browser_runtime["ready"]),
    )
    health = [
        ("Identities", len(identities)),
        ("Trending Audio", len(trending)),
        ("Blueprints", len(blueprints)),
        ("Content Packages", len(packages)),
        ("Distribution Records", len(records)),
    ]
    active_identity = _build_engagement_persona_payload(identities)
    latest_product = products[0] if products else None

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
        "distribution_records": _distribution_records_for_page,
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
        latest_run_response = _get_json(control_plane_base, "/pipeline/latest-run")
        latest_run = latest_run_response.get("run")
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
        latest_run = None
        control_plane_available = False

    latest_run_video_url = None
    latest_run_avatar_url = None
    latest_run_product_url = None
    if isinstance(latest_run, dict):
        if latest_run.get("run_id") and latest_run.get("video_path"):
            latest_run_video_url = url_for("artifact_video", run_id=latest_run["run_id"])
        latest_run_avatar_url = _file_path_to_static_url(latest_run.get("avatar_image_path"))
        latest_run_product_url = _file_path_to_static_url(latest_run.get("product_image_path"))

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
        "latest_run": latest_run,
        "latest_run_video_url": latest_run_video_url,
        "latest_run_avatar_url": latest_run_avatar_url,
        "latest_run_product_url": latest_run_product_url,
        "readiness": _readiness_state(),
        "browser_runtime": browser_runtime,
        "demo_run_mode": demo_run_mode,
        "active_identity": active_identity,
        "latest_product": latest_product,
        "latest_directive": latest_directive,
        "redo_pending": redo_pending,
    }
    return render_template("owner/demo.html", **ctx)


def _render_preview(api: str | None) -> Any:
    del api

    preview_records, control_plane_available = _load_preview_records(limit=24)
    selected_preview_id = (request.args.get("preview_id") or "").strip()
    if not preview_records:
        selected = None
    elif selected_preview_id:
        selected = next(
            (record for record in preview_records if str(record.get("preview_id")) == selected_preview_id),
            preview_records[0],
        )
    else:
        selected = preview_records[0]

    selected_json = json.dumps(selected, indent=2, default=str) if selected else ""
    return render_template(
        "owner/preview.html",
        **_nav_context("preview"),
        page_title="Generated Video Preview",
        control_plane_base=_control_plane_base(),
        control_plane_available=control_plane_available,
        preview_records=preview_records,
        selected_preview=selected,
        selected_json=selected_json,
    )


def _render_databases() -> Any:
    control_plane_base = _control_plane_base()
    selected_db_key = (request.args.get("db") or "").strip()
    selected_table = (request.args.get("table") or "").strip() or None
    page_num = max(request.args.get("page", default=1, type=int), 1)

    try:
        listing = _get_json(control_plane_base, "/pipeline/databases")
        databases = listing.get("databases", [])
        if not selected_db_key and databases:
            selected_db_key = str(databases[0].get("db_key") or "")
        detail = None
        if selected_db_key:
            detail = _get_json(
                control_plane_base,
                f"/pipeline/databases/{selected_db_key}?page={page_num}"
                + (f"&table={selected_table}" if selected_table else ""),
            ).get("database")
        control_plane_available = True
    except httpx.HTTPError:
        databases = []
        detail = None
        control_plane_available = False

    return render_template(
        "owner/databases.html",
        **_nav_context("databases"),
        page_title="Databases",
        control_plane_base=control_plane_base,
        control_plane_available=control_plane_available,
        databases=databases,
        selected_db_key=selected_db_key,
        selected_table=selected_table,
        detail=detail,
    )


app = create_app()


def main() -> None:
    port = int(os.environ.get("DASHBOARD_PORT", "8501"))
    app.run(
        host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1", use_reloader=False
    )


if __name__ == "__main__":
    main()
