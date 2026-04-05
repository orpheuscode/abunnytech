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
from browser_runtime.types import AgentTask
from hackathon_pipelines.adapters.facade import BrowserProviderFacade
from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, TwelveLabsUnderstanding
from hackathon_pipelines.pipelines.reel_discovery import (
    ReelDiscoveryPipeline,
    _build_reel_discovery_task,
    _parse_reels_from_agent,
)
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore, SQLiteReelSink, SQLiteTemplateStore
from integration.local_instagram_browser import ensure_profile_clone, launch_local_debug_chrome

ATTEMPTS = 4
SOURCE_USER_DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
PROFILE_DIRECTORY = "Profile 4"
RUNTIME_USER_DATA_DIR = ROOT / "data" / "chrome_test_instagram_runtime"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def build_task() -> AgentTask:
    return AgentTask(
        description=_build_reel_discovery_task(),
        max_steps=40,
        metadata={
            "pipeline": "reel_discovery",
            "browser_use": {
                "use_vision": True,
                "vision_detail_level": "high",
                "step_timeout": 180,
                "llm_timeout": 120,
                "max_actions_per_step": 5,
                "extend_system_message": (
                    "For Instagram discovery tasks, do not stop early. "
                    "You must inspect the visible feed, scroll, and continue gathering unique reels "
                    "before using done. When the page appears blank, treat it as a loading or SPA state "
                    "and recover by waiting or revisiting the Reels route."
                ),
            },
        },
    )


async def run_attempt(attempt: int) -> dict[str, object]:
    port = 9550 + attempt
    ensure_profile_clone(
        source_user_data_dir=SOURCE_USER_DATA_DIR,
        profile_directory=PROFILE_DIRECTORY,
        target_user_data_dir=RUNTIME_USER_DATA_DIR,
        refresh=False,
    )
    chrome_process, cdp_url = await launch_local_debug_chrome(
        cdp_port=port,
        user_data_dir=RUNTIME_USER_DATA_DIR,
        profile_directory=PROFILE_DIRECTORY,
    )
    provider = BrowserUseProvider(
        llm_model="ChatBrowserUse",
        dry_run=False,
        browser_config=BrowserUseBrowserConfig(cdp_url=cdp_url, keep_alive=True),
    )

    browser_result = await provider.run_agent_task(build_task())
    metrics = _parse_reels_from_agent(browser_result)

    db_path = ROOT / "data" / f"local_partial_pipeline_retry_attempt_{attempt}.sqlite3"
    store = SQLiteHackathonStore(db_path)
    templates = SQLiteTemplateStore(store=store)
    reel_sink = SQLiteReelSink(store=store)
    pipeline = ReelDiscoveryPipeline(
        browser=BrowserProviderFacade(provider),
        video_understanding=TwelveLabsUnderstanding(dry_run=False),
        templates=templates,
        reel_sink=reel_sink,
        gemini=GeminiTemplateAgent(dry_run=False),
        seed_metrics_loader=lambda: metrics,
    )

    pipeline_error = None
    created_templates = []
    if metrics:
        try:
            created_templates = await pipeline.run_discovery_cycle()
        except Exception as exc:
            pipeline_error = f"{type(exc).__name__}: {exc}"
    else:
        pipeline_error = "No structured reels returned by Browser Use discovery."

    report = {
        "attempt": attempt,
        "cdp_url": cdp_url,
        "runtime_user_data_dir": str(RUNTIME_USER_DATA_DIR),
        "db_path": str(db_path),
        "browser_success": browser_result.success,
        "browser_error": browser_result.error,
        "parsed_metrics_count": len(metrics),
        "parsed_metrics": [metric.model_dump(mode="json") for metric in metrics],
        "created_templates_count": len(created_templates),
        "created_templates": [tpl.model_dump(mode="json") for tpl in created_templates],
        "stored_reels_count": len(store.list_reel_metrics()),
        "stored_structures_count": len(store.list_structures()),
        "stored_templates_count": len(store.list_templates()),
        "pipeline_error": pipeline_error,
        "trace": browser_result.output.get("trace"),
        "final_result": browser_result.output.get("final_result"),
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
        if report["parsed_metrics_count"] or report["created_templates_count"]:
            print(json.dumps({"status": "success", "reports": reports}, indent=2))
            return
    print(json.dumps({"status": "failed", "reports": reports}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
