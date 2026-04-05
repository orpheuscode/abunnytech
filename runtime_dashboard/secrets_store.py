"""Persist owner API keys locally for the Flask dashboard and demo launcher.

Values are written to ``runtime_dashboard/.owner_secrets.json`` (gitignored).
``scripts/demo.py`` merges these into the environment for child processes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from packages.shared.browser_runtime_config import (
    ENV_BROWSER_USE_CDP_URL,
    ENV_BROWSER_USE_HEADLESS,
    ENV_CHROME_EXECUTABLE_PATH,
    ENV_CHROME_PROFILE_DIRECTORY,
    ENV_CHROME_USER_DATA_DIR,
    build_effective_browser_runtime_env,
)

_STORE_PATH = Path(__file__).resolve().parent / ".owner_secrets.json"

# Canonical env keys consumed by browser-runtime, hackathon pipelines, etc.
ENV_BROWSER_USE_PRIMARY = "BROWSER_USE_API_KEY"
ENV_GEMINI_PRIMARY = "GOOGLE_API_KEY"
ENV_GEMINI_ALT = "GEMINI_API_KEY"
ENV_TWELVE_PRIMARY = "TWELVE_LABS_API_KEY"
ENV_TWELVE_ALT = "TWELVELABS_API_KEY"
ENV_SELECTED_AVATAR_PATH = "OWNER_SELECTED_AVATAR_PATH"
ENV_SELECTED_PRODUCT_KEY = "OWNER_SELECTED_PRODUCT_KEY"


def secrets_path() -> Path:
    return _STORE_PATH


def read_raw() -> dict[str, str]:
    if not _STORE_PATH.is_file():
        return {}
    try:
        raw = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def to_environ_map(
    *,
    browser_use_api_key: str = "",
    gemini: str = "",
    twelvelabs: str = "",
    browser_use_cdp_url: str = "",
    chrome_executable_path: str = "",
    chrome_user_data_dir: str = "",
    chrome_profile_directory: str = "",
    browser_use_headless: str = "",
) -> dict[str, str]:
    """Map UI fields to process environment variable names."""
    m: dict[str, str] = {}
    bu = browser_use_api_key.strip()
    gm = gemini.strip()
    tl = twelvelabs.strip()
    if bu:
        m[ENV_BROWSER_USE_PRIMARY] = bu
    if gm:
        m[ENV_GEMINI_PRIMARY] = gm
        m[ENV_GEMINI_ALT] = gm
    if tl:
        m[ENV_TWELVE_PRIMARY] = tl
        m[ENV_TWELVE_ALT] = tl
    cdp = browser_use_cdp_url.strip()
    chrome_path = chrome_executable_path.strip()
    chrome_user_data = chrome_user_data_dir.strip()
    chrome_profile = chrome_profile_directory.strip()
    headless = browser_use_headless.strip().lower()
    if cdp:
        m[ENV_BROWSER_USE_CDP_URL] = cdp
    if chrome_path:
        m[ENV_CHROME_EXECUTABLE_PATH] = chrome_path
    if chrome_user_data:
        m[ENV_CHROME_USER_DATA_DIR] = chrome_user_data
    if chrome_profile:
        m[ENV_CHROME_PROFILE_DIRECTORY] = chrome_profile
    if headless in {"true", "false"}:
        m[ENV_BROWSER_USE_HEADLESS] = headless
    return m


def read_for_subprocess() -> dict[str, str]:
    """Env vars to inject when spawning API / control plane (from disk)."""
    raw = read_raw()
    merged = dict(raw)
    merged.update(build_effective_browser_runtime_env(saved=raw, environ=os.environ))
    return merged


def save_merged(
    *,
    browser_use_api_key: str,
    gemini: str,
    twelvelabs: str,
    browser_use_cdp_url: str = "",
    chrome_executable_path: str = "",
    chrome_user_data_dir: str = "",
    chrome_profile_directory: str = "",
    browser_use_headless: str = "",
) -> dict[str, str]:
    """Non-empty form fields overwrite; empty fields keep the previous value on disk."""
    nxt = dict(read_raw())
    patch = to_environ_map(
        browser_use_api_key=browser_use_api_key,
        gemini=gemini,
        twelvelabs=twelvelabs,
        browser_use_cdp_url=browser_use_cdp_url,
        chrome_executable_path=chrome_executable_path,
        chrome_user_data_dir=chrome_user_data_dir,
        chrome_profile_directory=chrome_profile_directory,
        browser_use_headless=browser_use_headless,
    )
    nxt.update(patch)
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(nxt, indent=2) + "\n", encoding="utf-8")
    return nxt


def save_raw_values(values: dict[str, str | None]) -> dict[str, str]:
    nxt = dict(read_raw())
    for key, value in values.items():
        if value is None or not str(value).strip():
            nxt.pop(key, None)
        else:
            nxt[key] = str(value).strip()
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(nxt, indent=2) + "\n", encoding="utf-8")
    return nxt


def apply_to_environ(updates: dict[str, str], *, overwrite: bool = False) -> None:
    for k, v in updates.items():
        if not v:
            continue
        if overwrite or not os.environ.get(k):
            os.environ[k] = v
