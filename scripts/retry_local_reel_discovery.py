# ruff: noqa: E402

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "browser_runtime"))
sys.path.insert(0, str(ROOT / "packages" / "hackathon_pipelines" / "src"))

from browser_runtime.providers.browser_use import BrowserUseBrowserConfig, BrowserUseProvider
from hackathon_pipelines.contracts import ReelSurfaceMetrics
from hackathon_pipelines.pipelines.reel_discovery import (
    ReelDiscoverySearchConfig,
    run_parallel_reel_discovery,
)
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore
from integration.local_instagram_browser import (
    ensure_profile_clone,
    launch_local_debug_chrome,
    wait_for_cdp,
)

ATTEMPTS = int(os.getenv("DISCOVERY_ATTEMPTS", "4"))
MIN_LIKES = int(os.getenv("DISCOVERY_MIN_LIKES", "500"))
MIN_COMMENTS = int(os.getenv("DISCOVERY_MIN_COMMENTS", "20"))


def _default_chrome_user_data_dir() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        return Path(localappdata) / "Google" / "Chrome" / "User Data"
    return Path.home() / ".config" / "google-chrome"


SOURCE_USER_DATA_DIR = Path(os.environ.get("CHROME_USER_DATA_DIR", _default_chrome_user_data_dir()))
PROFILE_DIRECTORY = os.environ.get("CHROME_PROFILE_DIRECTORY", "Profile 4")
CHROME_EXECUTABLE_PATH = Path(
    os.environ.get(
        "CHROME_EXECUTABLE_PATH",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe" if os.name == "nt" else "/usr/bin/google-chrome",
    )
)
RUNTIME_USER_DATA_DIR = ROOT / "data" / "chrome_test_instagram_runtime"
EXISTING_CDP_URLS = ("http://127.0.0.1:9553", "http://127.0.0.1:9666")


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _qualifying_reels(metrics: list[ReelSurfaceMetrics]) -> list[ReelSurfaceMetrics]:
    qualifying: list[ReelSurfaceMetrics] = []
    for metric in metrics:
        if metric.is_ugc_candidate is not True:
            continue
        if metric.likes < MIN_LIKES or metric.comments < MIN_COMMENTS:
            continue
        qualifying.append(metric)
    return qualifying


def _db_path_for_attempt(attempt: int) -> Path:
    override = os.getenv("REEL_QUEUE_DB_PATH", "").strip()
    if override:
        return Path(override)
    return ROOT / "data" / f"instagram_reel_queue_attempt_{attempt}.sqlite3"


async def run_attempt(attempt: int) -> dict[str, object]:
    port = 9665 + attempt
    for existing_cdp_url in EXISTING_CDP_URLS:
        if await wait_for_cdp(existing_cdp_url, timeout_seconds=2.0):
            cdp_url = existing_cdp_url
            chrome_process = None
            break
    else:
        cdp_url = None
        chrome_process = None

    ensure_profile_clone(
        source_user_data_dir=SOURCE_USER_DATA_DIR,
        profile_directory=PROFILE_DIRECTORY,
        target_user_data_dir=RUNTIME_USER_DATA_DIR,
        refresh=False,
    )
    if cdp_url is None:
        chrome_process, cdp_url = await launch_local_debug_chrome(
            cdp_port=port,
            user_data_dir=RUNTIME_USER_DATA_DIR,
            profile_directory=PROFILE_DIRECTORY,
            chrome_path=CHROME_EXECUTABLE_PATH,
        )
    provider = BrowserUseProvider(
        llm_model="ChatBrowserUse",
        dry_run=False,
        browser_config=BrowserUseBrowserConfig(cdp_url=cdp_url, keep_alive=True),
    )

    browser_results_metrics, browser_results = await run_parallel_reel_discovery(
        browser=provider,
        search_config=ReelDiscoverySearchConfig(
            discovery_mode="feed_scroll",
            target_good_reels=5,
        ),
        max_steps=28,
        browser_runtime_env={
            "BROWSER_USE_CDP_URL": cdp_url,
            "CHROME_EXECUTABLE_PATH": str(CHROME_EXECUTABLE_PATH),
            "CHROME_USER_DATA_DIR": str(RUNTIME_USER_DATA_DIR),
            "CHROME_PROFILE_DIRECTORY": PROFILE_DIRECTORY,
            "BROWSER_USE_HEADLESS": "false",
        },
    )
    metrics = browser_results_metrics
    qualifying_metrics = _qualifying_reels(metrics)

    db_path = _db_path_for_attempt(attempt)
    store = SQLiteHackathonStore(db_path)
    store.upsert_reel_metrics(qualifying_metrics)

    report = {
        "attempt": attempt,
        "cdp_url": cdp_url,
        "chrome_executable_path": str(CHROME_EXECUTABLE_PATH),
        "source_user_data_dir": str(SOURCE_USER_DATA_DIR),
        "profile_directory": PROFILE_DIRECTORY,
        "runtime_user_data_dir": str(RUNTIME_USER_DATA_DIR),
        "db_path": str(db_path),
        "browser_success": any(result.success for result in browser_results),
        "browser_error": None
        if any(result.success for result in browser_results)
        else "; ".join(result.error or result.task_id for result in browser_results),
        "agent_count": len(browser_results),
        "parsed_metrics_count": len(metrics),
        "parsed_metrics": [metric.model_dump(mode="json") for metric in metrics],
        "queued_reels_count": len(qualifying_metrics),
        "queued_reels": [metric.model_dump(mode="json") for metric in qualifying_metrics],
        "stored_reels_count": len(store.list_reel_metrics()),
        "stored_structures_count": len(store.list_structures()),
        "next_step": "Use an external API downloader later to convert stored Instagram reel URLs into MP4s.",
        "agent_runs": [
            {
                "task_id": result.task_id,
                "success": result.success,
                "error": result.error,
                "trace": result.output.get("trace"),
                "final_result": result.output.get("final_result"),
            }
            for result in browser_results
        ],
        "trace": next((result.output.get("trace") for result in browser_results if result.output.get("trace")), None),
        "final_result": next(
            (result.output.get("final_result") for result in browser_results if result.output.get("final_result")),
            None,
        ),
    }

    try:
        chrome_process.terminate()
        await asyncio.sleep(2.0)
    except Exception:
        pass
    return report


async def main() -> None:
    load_env(ROOT / ".env")
    reports: list[dict[str, object]] = []
    for attempt in range(1, ATTEMPTS + 1):
        report = await run_attempt(attempt)
        reports.append(report)
        if report["queued_reels_count"]:
            print(json.dumps({"status": "success", "reports": reports}, indent=2))
            return
    print(json.dumps({"status": "failed", "reports": reports}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
