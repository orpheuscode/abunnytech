"""Helpers for launching a local Chrome profile for Browser Use Instagram runs."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import httpx

DEFAULT_CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


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


def ensure_profile_clone(
    *,
    source_user_data_dir: str | Path,
    profile_directory: str,
    target_user_data_dir: str | Path,
    refresh: bool = False,
) -> Path:
    """Refresh a standalone Chrome user-data dir with one copied profile."""

    source_root = Path(source_user_data_dir)
    target_root = Path(target_user_data_dir)
    profile_source = source_root / profile_directory
    if not profile_source.exists():
        raise FileNotFoundError(profile_source)

    if target_root.exists() and not refresh:
        return target_root
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    for file_name in ("Local State", "First Run"):
        source_file = source_root / file_name
        if source_file.exists():
            shutil.copy2(source_file, target_root / file_name)
    shutil.copytree(profile_source, target_root / profile_directory)
    return target_root


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
