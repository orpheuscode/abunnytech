"""Shared Browser Use runtime configuration helpers.

These helpers keep the dashboard, demo launcher, and hackathon pipeline aligned
on how Browser Use should locate a live Chrome/CDP session.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

ENV_BROWSER_USE_CDP_URL = "BROWSER_USE_CDP_URL"
ENV_BROWSER_USE_HEADLESS = "BROWSER_USE_HEADLESS"
ENV_BROWSER_USE_USE_CLOUD = "BROWSER_USE_USE_CLOUD"
ENV_BROWSER_USE_CLOUD_PROFILE_ID = "BROWSER_USE_CLOUD_PROFILE_ID"
ENV_BROWSER_USE_CLOUD_PROXY_COUNTRY_CODE = "BROWSER_USE_CLOUD_PROXY_COUNTRY_CODE"
ENV_BROWSER_USE_LOCAL_PROFILE_MODE = "BROWSER_USE_LOCAL_PROFILE_MODE"
ENV_CHROME_EXECUTABLE_PATH = "CHROME_EXECUTABLE_PATH"
ENV_CHROME_USER_DATA_DIR = "CHROME_USER_DATA_DIR"
ENV_CHROME_PROFILE_DIRECTORY = "CHROME_PROFILE_DIRECTORY"

BROWSER_RUNTIME_ENV_KEYS: tuple[str, ...] = (
    ENV_BROWSER_USE_CDP_URL,
    ENV_BROWSER_USE_HEADLESS,
    ENV_BROWSER_USE_USE_CLOUD,
    ENV_BROWSER_USE_CLOUD_PROFILE_ID,
    ENV_BROWSER_USE_CLOUD_PROXY_COUNTRY_CODE,
    ENV_BROWSER_USE_LOCAL_PROFILE_MODE,
    ENV_CHROME_EXECUTABLE_PATH,
    ENV_CHROME_USER_DATA_DIR,
    ENV_CHROME_PROFILE_DIRECTORY,
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _pick(mapping: Mapping[str, str], key: str) -> str:
    return _clean(mapping.get(key))


def _default_chrome_user_data_dir() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if sys_platform() == "darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    return Path.home() / ".config" / "google-chrome"


def sys_platform() -> str:
    return os.getenv("PYTHON_SYS_PLATFORM_OVERRIDE") or os.sys.platform


def _chrome_executable_candidates() -> list[Path]:
    candidates: list[Path] = []
    which_candidates = [
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    candidates.extend(Path(path) for path in which_candidates if path)

    if os.name == "nt":
        candidates.extend(
            [
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            ]
        )
    elif sys_platform() == "darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    else:
        candidates.extend(
            [
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/google-chrome-stable"),
                Path("/usr/bin/chromium"),
                Path("/usr/bin/chromium-browser"),
            ]
        )
    return candidates


def detect_local_chrome_executable() -> str | None:
    for candidate in _chrome_executable_candidates():
        if candidate.exists():
            return str(candidate)
    return None


def detect_local_chrome_user_data_dir() -> str | None:
    candidate = _default_chrome_user_data_dir()
    if candidate.exists():
        return str(candidate)
    return None


def detect_local_chrome_profile_directory(user_data_dir: str | Path | None = None) -> str | None:
    root = Path(user_data_dir).expanduser() if user_data_dir else None
    if root is None or not root.is_dir():
        return None

    profiles = [
        child
        for child in root.iterdir()
        if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile "))
    ]
    if not profiles:
        return None
    selected = max(profiles, key=lambda item: item.stat().st_mtime)
    return selected.name


def normalize_chrome_user_data_root(
    user_data_dir: str | Path | None,
    *,
    profile_directory: str | None = None,
) -> str:
    """Ensure Chrome gets the user-data root, not a nested profile directory."""

    raw = _clean(user_data_dir)
    if not raw:
        return ""

    path = Path(raw).expanduser()
    profile = _clean(profile_directory)
    if path.name == "Default" or path.name.startswith("Profile "):
        path = path.parent
    elif profile and path.name.lower() == profile.lower():
        path = path.parent

    return os.path.normpath(str(path))


def resolve_local_chrome_profile_directory(
    profile_query: str | None,
    *,
    user_data_dir: str | Path | None = None,
) -> str | None:
    query = _clean(profile_query)
    if not query:
        return None

    root = Path(user_data_dir).expanduser() if user_data_dir else None
    if root is None or not root.is_dir():
        return query

    profiles = [
        child.name
        for child in root.iterdir()
        if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile "))
    ]
    if not profiles:
        return query

    if query in profiles:
        return query

    lowered = {name.lower(): name for name in profiles}
    if query.lower() in lowered:
        return lowered[query.lower()]

    digits = "".join(ch for ch in query if ch.isdigit())
    if digits:
        candidate = f"Profile {int(digits)}"
        if candidate in profiles:
            return candidate

    normalized_query = " ".join(query.lower().split())
    for name in profiles:
        if normalized_query == " ".join(name.lower().split()):
            return name

    return query


def detect_local_browser_runtime_env() -> dict[str, str]:
    user_data_dir = detect_local_chrome_user_data_dir()
    profile_directory = detect_local_chrome_profile_directory(user_data_dir)
    executable_path = detect_local_chrome_executable()

    detected: dict[str, str] = {}
    if executable_path:
        detected[ENV_CHROME_EXECUTABLE_PATH] = executable_path
    if user_data_dir:
        detected[ENV_CHROME_USER_DATA_DIR] = user_data_dir
    if profile_directory:
        detected[ENV_CHROME_PROFILE_DIRECTORY] = profile_directory
    return detected


def has_browser_runtime_config(values: Mapping[str, str] | None) -> bool:
    if values is None:
        return False
    if _pick(values, ENV_BROWSER_USE_CDP_URL):
        return True
    use_cloud = _pick(values, ENV_BROWSER_USE_USE_CLOUD).lower() == "true"
    if use_cloud or _pick(values, ENV_BROWSER_USE_CLOUD_PROFILE_ID):
        return True
    return all(
        _pick(values, key)
        for key in (
            ENV_CHROME_EXECUTABLE_PATH,
            ENV_CHROME_USER_DATA_DIR,
            ENV_CHROME_PROFILE_DIRECTORY,
        )
    )


def build_effective_browser_runtime_env(
    *,
    saved: Mapping[str, str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    effective: dict[str, str] = {}
    env = environ or os.environ
    raw_saved = saved or {}

    for key in BROWSER_RUNTIME_ENV_KEYS:
        value = _pick(env, key)
        if value:
            effective[key] = value

    for key in BROWSER_RUNTIME_ENV_KEYS:
        if key in effective:
            continue
        value = _pick(raw_saved, key)
        if value:
            effective[key] = value

    if _pick(effective, ENV_BROWSER_USE_CLOUD_PROFILE_ID) and ENV_BROWSER_USE_USE_CLOUD not in effective:
        effective[ENV_BROWSER_USE_USE_CLOUD] = "true"

    if not has_browser_runtime_config(effective):
        for key, value in detect_local_browser_runtime_env().items():
            if value and key not in effective:
                effective[key] = value

    if not effective.get(ENV_BROWSER_USE_CDP_URL) and effective.get(ENV_BROWSER_USE_USE_CLOUD, "").lower() != "true":
        detected_user_data_dir = (
            effective.get(ENV_CHROME_USER_DATA_DIR) or detect_local_chrome_user_data_dir()
        )
        if detected_user_data_dir and ENV_CHROME_USER_DATA_DIR not in effective:
            effective[ENV_CHROME_USER_DATA_DIR] = detected_user_data_dir

        resolved_profile = resolve_local_chrome_profile_directory(
            effective.get(ENV_CHROME_PROFILE_DIRECTORY) or None,
            user_data_dir=detected_user_data_dir,
        )
        if resolved_profile:
            effective[ENV_CHROME_PROFILE_DIRECTORY] = resolved_profile

        if ENV_CHROME_EXECUTABLE_PATH not in effective:
            executable_path = detect_local_chrome_executable()
            if executable_path:
                effective[ENV_CHROME_EXECUTABLE_PATH] = executable_path

    if ENV_BROWSER_USE_HEADLESS not in effective:
        effective[ENV_BROWSER_USE_HEADLESS] = "false"
    if ENV_BROWSER_USE_USE_CLOUD not in effective:
        effective[ENV_BROWSER_USE_USE_CLOUD] = "false"
    if ENV_BROWSER_USE_LOCAL_PROFILE_MODE not in effective:
        effective[ENV_BROWSER_USE_LOCAL_PROFILE_MODE] = "managed_runtime"

    return effective
