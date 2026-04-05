"""Persist owner API keys locally for the Flask dashboard and demo launcher.

Values are written to ``runtime_dashboard/.owner_secrets.json`` (gitignored).
``scripts/demo.py`` merges these into the environment for child processes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_STORE_PATH = Path(__file__).resolve().parent / ".owner_secrets.json"

# Canonical env keys consumed by browser-runtime, hackathon pipelines, etc.
ENV_BROWSER_USE_OPENAI = "OPENAI_API_KEY"
ENV_GEMINI_PRIMARY = "GOOGLE_API_KEY"
ENV_GEMINI_ALT = "GEMINI_API_KEY"
ENV_TWELVE_PRIMARY = "TWELVE_LABS_API_KEY"
ENV_TWELVE_ALT = "TWELVELABS_API_KEY"


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
    browser_use_openai: str = "",
    gemini: str = "",
    twelvelabs: str = "",
) -> dict[str, str]:
    """Map UI fields to process environment variable names."""
    m: dict[str, str] = {}
    bu = browser_use_openai.strip()
    gm = gemini.strip()
    tl = twelvelabs.strip()
    if bu:
        m[ENV_BROWSER_USE_OPENAI] = bu
    if gm:
        m[ENV_GEMINI_PRIMARY] = gm
        m[ENV_GEMINI_ALT] = gm
    if tl:
        m[ENV_TWELVE_PRIMARY] = tl
        m[ENV_TWELVE_ALT] = tl
    return m


def read_for_subprocess() -> dict[str, str]:
    """Env vars to inject when spawning API / control plane (from disk)."""
    return read_raw()


def save_merged(
    *,
    browser_use_openai: str,
    gemini: str,
    twelvelabs: str,
) -> dict[str, str]:
    """Non-empty form fields overwrite; empty fields keep the previous value on disk."""
    nxt = dict(read_raw())
    patch = to_environ_map(
        browser_use_openai=browser_use_openai,
        gemini=gemini,
        twelvelabs=twelvelabs,
    )
    nxt.update(patch)
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(nxt, indent=2) + "\n", encoding="utf-8")
    return nxt


def apply_to_environ(updates: dict[str, str]) -> None:
    for k, v in updates.items():
        if v:
            os.environ[k] = v
