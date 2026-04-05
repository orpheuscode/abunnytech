from __future__ import annotations

import sqlite3
from pathlib import Path

from integration import local_instagram_browser
from integration.local_instagram_browser import ensure_profile_clone, profile_has_instagram_session


def _write_cookie_db(root: Path, profile_directory: str, cookie_names: list[str]) -> None:
    profile_root = root / profile_directory / "Network"
    profile_root.mkdir(parents=True, exist_ok=True)
    db_path = profile_root / "Cookies"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE cookies (
                host_key TEXT,
                name TEXT,
                encrypted_value BLOB,
                value TEXT,
                is_persistent INTEGER,
                expires_utc INTEGER
            )
            """
        )
        for name in cookie_names:
            conn.execute(
                """
                INSERT INTO cookies (host_key, name, encrypted_value, value, is_persistent, expires_utc)
                VALUES (?, ?, X'01', '', 1, 0)
                """,
                (".instagram.com", name),
            )
        conn.commit()


def test_profile_has_instagram_session_detects_required_cookies(tmp_path: Path) -> None:
    root = tmp_path / "source"
    _write_cookie_db(root, "Profile 4", ["sessionid", "ds_user_id", "csrftoken"])

    assert profile_has_instagram_session(root, "Profile 4") is True


def test_ensure_profile_clone_preserves_existing_runtime_when_refresh_is_false(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    profile_directory = "Profile 4"

    source_root.mkdir(parents=True, exist_ok=True)
    target_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Local State").write_text("{}", encoding="utf-8")
    (target_root / "Local State").write_text("{}", encoding="utf-8")

    source_profile = source_root / profile_directory
    target_profile = target_root / profile_directory
    source_profile.mkdir(parents=True, exist_ok=True)
    target_profile.mkdir(parents=True, exist_ok=True)
    (source_profile / "marker.txt").write_text("fresh", encoding="utf-8")
    (target_profile / "marker.txt").write_text("stale", encoding="utf-8")

    ensure_profile_clone(
        source_user_data_dir=source_root,
        profile_directory=profile_directory,
        target_user_data_dir=target_root,
        refresh=False,
    )

    assert (target_root / profile_directory / "marker.txt").read_text(encoding="utf-8") == "stale"
