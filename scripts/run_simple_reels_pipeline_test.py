# ruff: noqa: E402

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "browser_runtime"))
sys.path.insert(0, str(ROOT / "packages" / "hackathon_pipelines" / "src"))

from browser_runtime.providers.browser_use import BrowserUseProvider
from hackathon_pipelines.adapters.facade import BrowserProviderFacade
from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, TwelveLabsUnderstanding
from hackathon_pipelines.contracts import ReelDiscoveryThresholds, ReelSurfaceMetrics
from hackathon_pipelines.pipelines.reel_discovery import ReelDiscoveryPipeline
from hackathon_pipelines.stores.sqlite_store import (
    SQLiteHackathonStore,
    SQLiteReelSink,
    SQLiteTemplateStore,
)
from integration.local_instagram_browser import (
    DEFAULT_CHROME_PATH,
    ensure_profile_clone,
    launch_local_debug_chrome,
    wait_for_cdp,
)

def _default_chrome_user_data_dir() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        return Path(localappdata) / "Google" / "Chrome" / "User Data"
    return Path.home() / ".config" / "google-chrome"


SOURCE_USER_DATA_DIR = Path(os.environ.get("CHROME_USER_DATA_DIR", _default_chrome_user_data_dir()))
PROFILE_DIRECTORY = os.environ.get("CHROME_PROFILE_DIRECTORY", "Profile 4")
CHROME_EXECUTABLE_PATH = Path(os.environ.get("CHROME_EXECUTABLE_PATH", str(DEFAULT_CHROME_PATH)))
RUNTIME_USER_DATA_DIR = ROOT / "data" / "chrome_test_instagram_runtime"
EXISTING_CDP_URLS = ("http://127.0.0.1:9553", "http://127.0.0.1:9666")
TARGET_REELS_TO_SCRAPE = 5
TARGET_REELS_TO_PROCESS = 1


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _fetch_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_probable_video_download_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    url = value.strip()
    if not url.startswith(("http://", "https://")):
        return False
    lowered = url.lower()
    path = urlparse(url).path.lower()
    if path.endswith((".css", ".js", ".woff", ".woff2", ".ttf", ".otf", ".svg", ".png", ".jpg", ".jpeg", ".webp")):
        return False
    if "mime=audio" in lowered or "mime_type=audio" in lowered or "/audio/" in path:
        return False
    if path.endswith(".mp4"):
        return True
    return any(
        hint in lowered
        for hint in ("mime=video", "mime_type=video", "video_versions", "/video/", "/reel_media/", "/clips/", "/v/t")
    )


class BrowserTargetSession:
    """Minimal CDP client for a single Instagram page target."""

    def __init__(self, websocket: Any, session_id: str, target_id: str) -> None:
        self._websocket = websocket
        self._session_id = session_id
        self._target_id = target_id
        self._inner_id = 100

    @classmethod
    async def connect(cls, cdp_url: str) -> BrowserTargetSession:
        version = _fetch_json(cdp_url.rstrip("/") + "/json/version")
        websocket = await websockets.connect(version["webSocketDebuggerUrl"], max_size=None, open_timeout=10)

        async def browser_call(message_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
            await websocket.send(json.dumps({"id": message_id, "method": method, "params": params}))
            while True:
                raw = await asyncio.wait_for(websocket.recv(), timeout=10)
                message = json.loads(raw)
                if message.get("id") != message_id:
                    continue
                if "error" in message:
                    msg = message["error"].get("message", f"{method} failed")
                    raise RuntimeError(msg)
                return message["result"]

        create_result = await browser_call(1, "Target.createTarget", {"url": "about:blank"})
        target_id = create_result["targetId"]
        attach_result = await browser_call(2, "Target.attachToTarget", {"targetId": target_id, "flatten": False})
        session_id = attach_result["sessionId"]
        return cls(websocket, session_id=session_id, target_id=target_id)

    async def close(self) -> None:
        try:
            await self._websocket.send(
                json.dumps(
                    {
                        "id": 3,
                        "method": "Target.closeTarget",
                        "params": {"targetId": self._target_id},
                    }
                )
            )
        except Exception:
            pass
        await self._websocket.close()

    async def command(self, method: str, params: dict[str, Any] | None = None, *, timeout_seconds: float = 30.0) -> Any:
        self._inner_id += 1
        inner_id = self._inner_id
        inner = {
            "id": inner_id,
            "method": method,
            "params": params or {},
        }
        outer_id = inner_id + 100_000
        await self._websocket.send(
            json.dumps(
                {
                    "id": outer_id,
                    "method": "Target.sendMessageToTarget",
                    "params": {
                        "sessionId": self._session_id,
                        "message": json.dumps(inner),
                    },
                }
            )
        )
        while True:
            raw = await asyncio.wait_for(self._websocket.recv(), timeout=timeout_seconds)
            message = json.loads(raw)
            if message.get("method") != "Target.receivedMessageFromTarget":
                continue
            params = message.get("params", {})
            if params.get("sessionId") != self._session_id:
                continue
            inner_message = json.loads(params.get("message", "{}"))
            if inner_message.get("id") != inner_id:
                continue
            if "error" in inner_message:
                msg = inner_message["error"].get("message", "CDP Runtime.evaluate failed")
                raise RuntimeError(msg)
            return inner_message.get("result", {})

    async def evaluate(self, expression: str, *, timeout_seconds: float = 30.0) -> Any:
        result = await self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
            timeout_seconds=timeout_seconds,
        )
        return result.get("result", {}).get("value")

CURRENT_REEL_JS = r"""
(() => {
  const compactToInt = (value) => {
    if (!value) return 0;
    const raw = String(value).trim().replace(/,/g, '').toUpperCase();
    const match = raw.match(/^(\d+(?:\.\d+)?)([KMB])?$/);
    if (!match) return 0;
    const num = parseFloat(match[1]);
    const suffix = match[2] || '';
    const mult = suffix === 'K' ? 1_000 : suffix === 'M' ? 1_000_000 : suffix === 'B' ? 1_000_000_000 : 1;
    return Math.round(num * mult);
  };

  const sanitizeMediaUrl = (value) => {
    if (!value || !/^https?:/i.test(value)) return null;
    try {
      const url = new URL(value);
      url.searchParams.delete('bytestart');
      url.searchParams.delete('byteend');
      return url.toString();
    } catch {
      return value;
    }
  };

  const isLikelyVideoUrl = (value) => {
    if (!value || !/^https?:/i.test(value)) return false;
    try {
      const url = new URL(value);
      const path = url.pathname.toLowerCase();
      const raw = `${path}${url.search}`.toLowerCase();
      if (/\.(css|js|woff2?|ttf|otf|svg|png|jpe?g|webp|gif|ico)(?:$|[?#])/.test(path)) return false;
      if (/mime(_type)?=audio/.test(raw) || /\/audio\//.test(path)) return false;
      if (/\.mp4(?:$|[?#])/.test(path)) return true;
      return /(mime(_type)?=video|video_versions|\/video\/|\/reel_media\/|\/clips\/|\/v\/t)/.test(raw);
    } catch {
      return false;
    }
  };

  const resourceScore = (value) => {
    let score = 0;
    const raw = String(value || '').toLowerCase();
    if (raw.includes('.mp4')) score += 8;
    if (raw.includes('mime=video') || raw.includes('mime_type=video')) score += 6;
    if (raw.includes('dash_vp9') || raw.includes('1080p') || raw.includes('720p')) score += 5;
    if (raw.includes('clips')) score += 3;
    if (raw.includes('audio')) score -= 10;
    if (raw.includes('.css') || raw.includes('.js')) score -= 20;
    return score;
  };

  const bestVideoUrl = () => {
    const direct = Array.from(document.querySelectorAll('video'))
      .map((video) => video.currentSrc || video.src || '')
      .map((value) => sanitizeMediaUrl(value));
    const directMatch = direct.find((value) => isLikelyVideoUrl(value));
    if (directMatch) return directMatch;

    const meta = Array.from(document.querySelectorAll('meta[property="og:video"], meta[property="og:video:secure_url"], meta[name="twitter:player:stream"]'))
      .map((node) => sanitizeMediaUrl(node.content || ''))
      .find((value) => isLikelyVideoUrl(value));
    if (meta) return meta;

    const perf = performance
      .getEntriesByType('resource')
      .map((entry) => ({ name: sanitizeMediaUrl(entry.name), initiatorType: entry.initiatorType || '' }))
      .filter((entry) => isLikelyVideoUrl(entry.name))
      .sort((a, b) => (resourceScore(b.name) + (b.initiatorType === 'video' ? 4 : 0)) - (resourceScore(a.name) + (a.initiatorType === 'video' ? 4 : 0)))
      .map((entry) => entry.name);
    return perf[0] || null;
  };

  const extractVisibleStats = () => {
    const lines = (document.body?.innerText || '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 30);
    const numeric = lines.filter((line) => /^\d+(?:[.,]\d+)?[KMB]?$/i.test(line));
    return {
      likes: compactToInt(numeric[0] || 0),
      comments: compactToInt(numeric[1] || 0),
      views: 0,
      debug_lines: lines.slice(0, 12),
    };
  };

  const href = location.href;
  const reelMatch = href.match(/\/reel\/([^/?#]+)/) || href.match(/\/reels\/([^/?#]+)/);
  const reelId = reelMatch ? reelMatch[1] : '';
  const stats = extractVisibleStats();
  return {
    href,
    reel_id: reelId,
    source_url: href,
    video_download_url: bestVideoUrl(),
    views: stats.views,
    likes: stats.likes,
    comments: stats.comments,
    debug_lines: stats.debug_lines,
  };
})()
"""

HOME_STATE_JS = """
(() => ({
  href: location.href,
  title: document.title,
  reels_link_ready: !!document.querySelector('a[href="/reels/"]'),
  body_length: (document.body?.innerText || '').trim().length,
}))()
"""

CLICK_REELS_JS = """
(() => {
  const reelsLink = document.querySelector('a[href="/reels/"]');
  if (!reelsLink) return { clicked: false };
  reelsLink.click();
  return { clicked: true };
})()
"""

SCROLL_REELS_JS = """
(() => {
  const before = location.href;
  window.scrollBy(0, window.innerHeight * 0.95);
  return { before };
})()
"""


async def _safe_evaluate(
    session: BrowserTargetSession,
    expression: str,
    *,
    timeout_seconds: float,
    default: Any = None,
) -> Any:
    try:
        return await session.evaluate(expression, timeout_seconds=timeout_seconds)
    except Exception:
        return default


async def _resolve_cdp_url() -> tuple[str, Any | None]:
    for cdp_url in EXISTING_CDP_URLS:
        if await wait_for_cdp(cdp_url, timeout_seconds=2.0):
            return cdp_url, None

    ensure_profile_clone(
        source_user_data_dir=SOURCE_USER_DATA_DIR,
        profile_directory=PROFILE_DIRECTORY,
        target_user_data_dir=RUNTIME_USER_DATA_DIR,
        refresh=False,
    )
    chrome_process, cdp_url = await launch_local_debug_chrome(
        cdp_port=9666,
        user_data_dir=RUNTIME_USER_DATA_DIR,
        profile_directory=PROFILE_DIRECTORY,
        start_url="https://www.instagram.com/",
        chrome_path=CHROME_EXECUTABLE_PATH,
    )
    return cdp_url, chrome_process


async def scrape_instagram_reels_via_cdp(
    cdp_url: str,
    *,
    target_count: int = TARGET_REELS_TO_SCRAPE,
) -> tuple[list[ReelSurfaceMetrics], dict[str, Any]]:
    session = await BrowserTargetSession.connect(cdp_url)
    try:
        await session.evaluate("location.assign('https://www.instagram.com/'); 'ok'", timeout_seconds=10.0)

        home_state = None
        for _ in range(20):
            await asyncio.sleep(1.0)
            home_state = await _safe_evaluate(session, HOME_STATE_JS, timeout_seconds=15.0, default=None)
            if isinstance(home_state, dict) and home_state.get("reels_link_ready"):
                break
        else:
            raw_result = {
                "ok": False,
                "reason": "home_page_never_loaded_reels_link",
                "home_state": home_state,
                "reels": [],
            }
            return [], {
                "method": "raw_cdp_home_to_reels",
                "cdp_url": cdp_url,
                "target_id": session._target_id,
                "raw_result": raw_result,
            }

        click_result = await _safe_evaluate(session, CLICK_REELS_JS, timeout_seconds=10.0, default={"clicked": False})
        reels_state = None
        for _ in range(20):
            await asyncio.sleep(1.0)
            reels_state = await _safe_evaluate(session, HOME_STATE_JS, timeout_seconds=15.0, default=None)
            if (
                isinstance(reels_state, dict)
                and "/reels/" in str(reels_state.get("href", ""))
                and int(reels_state.get("body_length", 0)) > 20
            ):
                break
        else:
            raw_result = {
                "ok": False,
                "reason": "reels_page_never_loaded",
                "click_result": click_result,
                "reels_state": reels_state,
                "reels": [],
            }
            return [], {
                "method": "raw_cdp_home_to_reels",
                "cdp_url": cdp_url,
                "target_id": session._target_id,
                "raw_result": raw_result,
            }

        raw_reels: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for _ in range(target_count + 6):
            await asyncio.sleep(3.5)
            reel = await _safe_evaluate(session, CURRENT_REEL_JS, timeout_seconds=20.0, default=None)
            if isinstance(reel, dict):
                reel_id = str(reel.get("reel_id") or "").strip()
                if reel_id and reel_id not in seen_ids:
                    seen_ids.add(reel_id)
                    raw_reels.append(reel)
                    if len(raw_reels) >= target_count:
                        break

            await _safe_evaluate(
                session,
                SCROLL_REELS_JS,
                timeout_seconds=10.0,
                default={"before": ""},
            )
            await asyncio.sleep(4.0)

        raw_result = {
            "ok": bool(raw_reels),
            "home_state": home_state,
            "click_result": click_result,
            "reels_state": reels_state,
            "reels": raw_reels,
        }
    finally:
        await session.close()

    raw_reels = raw_result.get("reels", []) if isinstance(raw_result, dict) else []
    metrics: list[ReelSurfaceMetrics] = []
    for item in raw_reels:
        if not isinstance(item, dict):
            continue
        reel_id = str(item.get("reel_id") or "").strip()
        source_url = str(item.get("source_url") or "").strip()
        if not reel_id or not source_url:
            continue
        try:
            video_download_url = item.get("video_download_url")
            metrics.append(
                ReelSurfaceMetrics.model_validate(
                    {
                        "reel_id": reel_id,
                        "source_url": source_url,
                        "video_download_url": (
                            video_download_url if _is_probable_video_download_url(video_download_url) else None
                        ),
                        "views": int(item.get("views") or 0),
                        "likes": int(item.get("likes") or 0),
                        "comments": int(item.get("comments") or 0),
                    }
                )
            )
        except Exception:
            continue
    trace = {
        "method": "raw_cdp_home_to_reels",
        "cdp_url": cdp_url,
        "target_id": session._target_id,
        "raw_result": raw_result,
    }
    return metrics, trace


async def main() -> None:
    load_env(ROOT / ".env")

    cdp_url, chrome_process = await _resolve_cdp_url()
    metrics, discovery_trace = await scrape_instagram_reels_via_cdp(cdp_url)

    selected_metrics = sorted(
        [metric for metric in metrics if metric.video_download_url],
        key=lambda metric: (metric.likes, metric.comments),
        reverse=True,
    )[:TARGET_REELS_TO_PROCESS]

    db_path = ROOT / "data" / "simple_reels_pipeline_test.sqlite3"
    store = SQLiteHackathonStore(db_path)
    templates = SQLiteTemplateStore(store=store)
    reel_sink = SQLiteReelSink(store=store)
    pipeline = ReelDiscoveryPipeline(
        browser=BrowserProviderFacade(BrowserUseProvider(dry_run=True)),
        video_understanding=TwelveLabsUnderstanding(dry_run=False),
        templates=templates,
        reel_sink=reel_sink,
        gemini=GeminiTemplateAgent(dry_run=False),
        thresholds=ReelDiscoveryThresholds(min_views=0, min_likes=0, min_comments=0),
        seed_metrics_loader=lambda: selected_metrics,
    )

    pipeline_error = None
    created_templates = []
    if selected_metrics:
        try:
            created_templates = await pipeline.run_discovery_cycle()
        except Exception as exc:
            pipeline_error = f"{type(exc).__name__}: {exc}"
    else:
        pipeline_error = "No reels with a direct downloadable video URL were collected from CDP discovery."

    report = {
        "cdp_url": cdp_url,
        "chrome_executable_path": str(CHROME_EXECUTABLE_PATH),
        "source_user_data_dir": str(SOURCE_USER_DATA_DIR),
        "profile_directory": PROFILE_DIRECTORY,
        "runtime_user_data_dir": str(RUNTIME_USER_DATA_DIR),
        "db_path": str(db_path),
        "discovery_success": bool(metrics),
        "discovery_trace": discovery_trace,
        "discovered_reels_count": len(metrics),
        "discovered_reels": [metric.model_dump(mode="json") for metric in metrics],
        "selected_reels_count": len(selected_metrics),
        "selected_reels": [metric.model_dump(mode="json") for metric in selected_metrics],
        "created_templates_count": len(created_templates),
        "created_templates": [template.model_dump(mode="json") for template in created_templates],
        "stored_reels_count": len(store.list_reel_metrics()),
        "stored_structures_count": len(store.list_structures()),
        "stored_templates_count": len(store.list_templates()),
        "pipeline_error": pipeline_error,
    }
    print(json.dumps(report, indent=2))

    if chrome_process is not None:
        try:
            chrome_process.terminate()
            await asyncio.sleep(2.0)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
