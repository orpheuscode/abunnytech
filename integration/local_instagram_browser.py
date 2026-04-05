"""Helpers for launching a local Chrome profile for Browser Use Instagram runs."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import httpx

DEFAULT_CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
_INSTAGRAM_SESSION_COOKIE_NAMES = frozenset({"sessionid", "ds_user_id"})


async def wait_for_cdp(cdp_url: str, *, timeout_seconds: float = 20.0) -> bool:
    """Poll a local Chrome DevTools endpoint until it responds or times out."""

    version_url = cdp_url.rstrip("/") + "/json/version"
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    async with httpx.AsyncClient(timeout=3.0) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(version_url)
                response.raise_for_status()
                return True
            except Exception:
                await asyncio.sleep(1.0)
    return False


def _profile_cookie_db_candidates(user_data_dir: Path, profile_directory: str) -> list[Path]:
    profile_root = user_data_dir / profile_directory
    return [
        profile_root / "Network" / "Cookies",
        profile_root / "Cookies",
    ]


def _read_cookie_names(cookie_db_path: Path, *, host_fragment: str) -> set[str]:
    if not cookie_db_path.exists():
        return set()

    temp_copy = Path(tempfile.gettempdir()) / f"abunnytech_cookies_{uuid.uuid4().hex}.sqlite"
    try:
        shutil.copy2(cookie_db_path, temp_copy)
        conn = sqlite3.connect(temp_copy)
        try:
            rows = conn.execute(
                "SELECT name FROM cookies WHERE host_key LIKE ?",
                (f"%{host_fragment}%",),
            ).fetchall()
        finally:
            conn.close()
        return {str(row[0]) for row in rows}
    except Exception:
        return set()
    finally:
        try:
            temp_copy.unlink()
        except FileNotFoundError:
            pass


def profile_has_instagram_session(user_data_dir: str | Path, profile_directory: str) -> bool:
    """Return whether the profile currently holds Instagram auth session cookies."""

    root = Path(user_data_dir)
    cookie_names: set[str] = set()
    for candidate in _profile_cookie_db_candidates(root, profile_directory):
        cookie_names |= _read_cookie_names(candidate, host_fragment="instagram")
    return _INSTAGRAM_SESSION_COOKIE_NAMES.issubset(cookie_names)


def _rmtree_with_retries(path: Path, *, attempts: int = 5, delay_seconds: float = 0.2) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error


def ensure_profile_clone(
    *,
    source_user_data_dir: str | Path,
    profile_directory: str,
    target_user_data_dir: str | Path,
    refresh: bool = False,
) -> Path:
    """Bootstrap a standalone Chrome user-data dir with one copied profile.

    When ``refresh`` is ``False``, an existing runtime profile is always
    preserved so cookies and login state survive across relaunches. This keeps a
    dedicated automation profile stable once the user logs into Instagram there.
    """

    source_root = Path(source_user_data_dir)
    target_root = Path(target_user_data_dir)
    profile_source = source_root / profile_directory
    profile_target = target_root / profile_directory
    if not profile_source.exists():
        raise FileNotFoundError(profile_source)

    if target_root.exists() and profile_target.exists() and not refresh:
        return target_root
    if target_root.exists():
        _rmtree_with_retries(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    for file_name in ("Local State", "First Run"):
        source_file = source_root / file_name
        if source_file.exists():
            shutil.copy2(source_file, target_root / file_name)
    shutil.copytree(profile_source, target_root / profile_directory)
    return target_root


def close_all_chrome_processes(*, force: bool = True) -> None:
    """Best-effort shutdown for local Chrome processes before direct-profile launch."""

    if os.name == "nt":
        args = ["taskkill", "/IM", "chrome.exe"]
        if force:
            args.insert(1, "/F")
        subprocess.run(args, check=False, capture_output=True)
        return

    cmd = ["pkill"]
    if force:
        cmd.append("-9")
    cmd.extend(["-f", "chrome"])
    subprocess.run(cmd, check=False, capture_output=True)


async def launch_local_debug_chrome(
    *,
    cdp_port: int,
    user_data_dir: str | Path,
    profile_directory: str,
    start_url: str = "https://www.instagram.com/reels/",
    chrome_path: str | Path = DEFAULT_CHROME_PATH,
) -> tuple[subprocess.Popen[bytes], str]:
    """Launch Chrome with remote debugging and wait until CDP is available."""

    chrome_exe = Path(chrome_path)
    if not chrome_exe.exists():
        raise FileNotFoundError(chrome_exe)

    cdp_url = f"http://127.0.0.1:{cdp_port}"
    args = [
        str(chrome_exe),
        f"--remote-debugging-port={cdp_port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={Path(user_data_dir)}",
        f"--profile-directory={profile_directory}",
        "--no-first-run",
        "--new-window",
        start_url,
    ]
    process = subprocess.Popen(args)
    ok = await wait_for_cdp(cdp_url)
    if not ok:
        process.terminate()
        raise RuntimeError(f"Chrome launched but CDP was unavailable at {cdp_url}")
    return process, cdp_url
