from __future__ import annotations

import os

from packages.shared import browser_runtime_config as runtime_config


def test_build_effective_browser_runtime_env_prefers_env_then_saved(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_config,
        "detect_local_browser_runtime_env",
        lambda: {
            runtime_config.ENV_CHROME_EXECUTABLE_PATH: "/auto/google-chrome",
            runtime_config.ENV_CHROME_USER_DATA_DIR: "/auto/user-data",
            runtime_config.ENV_CHROME_PROFILE_DIRECTORY: "Profile 4",
        },
    )

    effective = runtime_config.build_effective_browser_runtime_env(
        saved={
            runtime_config.ENV_CHROME_EXECUTABLE_PATH: "/saved/google-chrome",
            runtime_config.ENV_CHROME_PROFILE_DIRECTORY: "Profile 9",
        },
        environ={
            runtime_config.ENV_CHROME_USER_DATA_DIR: "/env/user-data",
        },
    )

    assert effective[runtime_config.ENV_CHROME_EXECUTABLE_PATH] == "/saved/google-chrome"
    assert effective[runtime_config.ENV_CHROME_USER_DATA_DIR] == "/env/user-data"
    assert effective[runtime_config.ENV_CHROME_PROFILE_DIRECTORY] == "Profile 9"
    assert effective[runtime_config.ENV_BROWSER_USE_HEADLESS] == "false"


def test_build_effective_browser_runtime_env_auto_detects_local_chrome(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_config,
        "detect_local_browser_runtime_env",
        lambda: {
            runtime_config.ENV_CHROME_EXECUTABLE_PATH: "/auto/google-chrome",
            runtime_config.ENV_CHROME_USER_DATA_DIR: "/auto/user-data",
            runtime_config.ENV_CHROME_PROFILE_DIRECTORY: "Profile 4",
        },
    )

    effective = runtime_config.build_effective_browser_runtime_env(saved={}, environ={})

    assert runtime_config.has_browser_runtime_config(effective) is True
    assert effective[runtime_config.ENV_CHROME_EXECUTABLE_PATH] == "/auto/google-chrome"
    assert effective[runtime_config.ENV_CHROME_PROFILE_DIRECTORY] == "Profile 4"
    assert effective[runtime_config.ENV_BROWSER_USE_HEADLESS] == "false"


def test_normalize_chrome_user_data_root_strips_profile_suffix() -> None:
    root = runtime_config.normalize_chrome_user_data_root(
        "/home/u/.config/google-chrome/Profile 3",
        profile_directory="Profile 3",
    )
    assert os.path.normpath(root) == os.path.normpath("/home/u/.config/google-chrome")


def test_normalize_chrome_user_data_root_unchanged_when_already_parent() -> None:
    root = runtime_config.normalize_chrome_user_data_root(
        "/home/u/.config/google-chrome",
        profile_directory="Profile 3",
    )
    assert os.path.normpath(root) == os.path.normpath("/home/u/.config/google-chrome")


def test_resolve_local_chrome_profile_directory_accepts_profile_number(tmp_path) -> None:
    (tmp_path / "Profile 9").mkdir()
    (tmp_path / "Default").mkdir()

    resolved = runtime_config.resolve_local_chrome_profile_directory(
        "9",
        user_data_dir=tmp_path,
    )

    assert resolved == "Profile 9"


def test_build_effective_browser_runtime_env_resolves_profile_query(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_config,
        "detect_local_chrome_user_data_dir",
        lambda: "/auto/user-data",
    )
    monkeypatch.setattr(
        runtime_config,
        "detect_local_chrome_executable",
        lambda: "/auto/google-chrome",
    )
    monkeypatch.setattr(
        runtime_config,
        "resolve_local_chrome_profile_directory",
        lambda profile_query, *, user_data_dir=None: "Profile 9",
    )

    effective = runtime_config.build_effective_browser_runtime_env(
        saved={runtime_config.ENV_CHROME_PROFILE_DIRECTORY: "9"},
        environ={},
    )

    assert effective[runtime_config.ENV_CHROME_USER_DATA_DIR] == "/auto/user-data"
    assert effective[runtime_config.ENV_CHROME_PROFILE_DIRECTORY] == "Profile 9"
