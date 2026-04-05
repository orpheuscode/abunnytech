"""Reel discovery: Browser Use → threshold → download → TwelveLabs → DB → Gemini template decision."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import tempfile
import uuid
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from browser_runtime.providers.browser_use import BrowserUseBrowserConfig, BrowserUseProvider
from browser_runtime.types import AgentResult, AgentTask, ProviderType
from integration.local_instagram_browser import ensure_profile_clone, launch_local_debug_chrome
from packages.shared.browser_runtime_config import (
    ENV_BROWSER_USE_CDP_URL,
    ENV_BROWSER_USE_HEADLESS,
    ENV_CHROME_EXECUTABLE_PATH,
    ENV_CHROME_PROFILE_DIRECTORY,
    ENV_CHROME_USER_DATA_DIR,
)
from pydantic import BaseModel, ConfigDict, Field

from hackathon_pipelines.adapters.facade import BrowserProviderFacade
from hackathon_pipelines.contracts import (
    ReelDiscoveryThresholds,
    ReelSurfaceMetrics,
    TemplateDisposition,
    VideoTemplateRecord,
)
from hackathon_pipelines.ports import (
    BrowserAutomationPort,
    GeminiVideoAgentPort,
    ReelMetadataSinkPort,
    TemplateStorePort,
    VideoUnderstandingPort,
)
from hackathon_pipelines.stores.memory import new_id

INSTAGRAM_REELS_FEED_URL = "https://www.instagram.com/reels/"
DEFAULT_DISCOVERY_AGENT_COUNT = 3
MAX_DISCOVERY_AGENT_COUNT = 6


class ReelDiscoverySearchConfig(BaseModel):
    """Controls how Instagram discovery should target creator-style content."""

    model_config = ConfigDict(extra="forbid")

    discovery_mode: Literal["feed_scroll", "hashtag_profiles"] = "feed_scroll"
    hashtags: list[str] = Field(
        default_factory=lambda: ["ugccreator", "contentcreator", "skincare", "beautyroutine"]
    )
    creator_focus_terms: list[str] = Field(
        default_factory=lambda: [
            "ugc creator",
            "creator talking to camera",
            "product demo",
            "testimonial",
            "before and after",
            "routine",
            "founder storytelling",
        ]
    )
    hashtag_scroll_passes: int = Field(default=3, ge=1, le=8)
    creator_candidates_to_open: int = Field(default=5, ge=1, le=12)
    reel_candidates_to_open: int = Field(default=8, ge=1, le=12)
    target_good_reels: int = Field(default=5, ge=1, le=12)


class BrowserUseDiscoveredReel(BaseModel):
    """Structured Browser Use discovery output for a single reel."""

    model_config = ConfigDict(extra="forbid")

    reel_id: str
    source_url: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    creator_handle: str | None = None
    caption_text: str | None = None
    is_ugc_candidate: bool | None = None
    ugc_reason: str | None = None
    video_download_url: str | None = None


class BrowserUseDiscoveredReels(BaseModel):
    """Structured Browser Use discovery payload."""

    model_config = ConfigDict(extra="forbid")

    reels: list[BrowserUseDiscoveredReel] = Field(default_factory=list)


def build_instagram_reels_browser_use_metadata() -> dict[str, Any]:
    """Shared Browser Use settings for discovery-only Instagram reel scrolling."""

    return {
        "pipeline": "reel_discovery",
        "browser_use": {
            "use_vision": True,
            "vision_detail_level": "high",
            "step_timeout": 180,
            "llm_timeout": 120,
            "max_actions_per_step": 3,
            "extend_system_message": (
                "For Instagram discovery tasks, stay inside instagram.com and start from the Reels feed only. "
                "Do not open search engines such as DuckDuckGo, Google, or Bing. "
                "do not visit downloader sites, do not search for 'instagram reel downloader', and do not try to "
                "obtain MP4/media URLs inside the browser. Discovery is metadata-only: inspect the current reel, "
                "capture visible metrics plus the canonical Instagram reel URL, then scroll to the next reel. "
                "Do not open creator profiles, do not open DMs, do not like/comment/share/save/follow, and do not "
                "click the More menu. If navigation leaves Instagram, go back immediately."
            ),
        },
        "browser_use_output_model_schema": BrowserUseDiscoveredReels,
    }


def _resolved_discovery_agent_count(agent_count: int | None = None) -> int:
    raw = agent_count
    if raw is None:
        raw = int(os.getenv("INSTAGRAM_DISCOVERY_AGENT_COUNT", str(DEFAULT_DISCOVERY_AGENT_COUNT)))
    return max(1, min(int(raw), MAX_DISCOVERY_AGENT_COUNT))


def _headless_browser_runtime(browser_runtime_env: Mapping[str, str] | None) -> bool:
    if not browser_runtime_env:
        return False
    return str(browser_runtime_env.get(ENV_BROWSER_USE_HEADLESS, "false")).strip().lower() == "true"


def _supports_parallel_local_windows(browser_runtime_env: Mapping[str, str] | None) -> bool:
    if not browser_runtime_env or _headless_browser_runtime(browser_runtime_env):
        return False
    return all(
        str(browser_runtime_env.get(key) or "").strip()
        for key in (
            ENV_CHROME_EXECUTABLE_PATH,
            ENV_CHROME_USER_DATA_DIR,
            ENV_CHROME_PROFILE_DIRECTORY,
        )
    )


def _cdp_start_port(browser_runtime_env: Mapping[str, str] | None) -> int:
    raw = str((browser_runtime_env or {}).get(ENV_BROWSER_USE_CDP_URL, "")).strip()
    if ":" in raw:
        try:
            return int(raw.rsplit(":", 1)[-1])
        except ValueError:
            return 9222
    return 9222


def _find_free_local_port(start_port: int) -> int:
    port = max(1024, start_port)
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                port += 1
                continue
            return port


def _discovery_worker_description(
    *,
    base_description: str,
    agent_index: int,
    agent_count: int,
) -> str:
    return (
        f"{base_description}\n\n"
        "Parallel worker note:\n"
        f"- You are discovery worker {agent_index + 1} of {agent_count}.\n"
        "- Prefer unique reels that are different from what other workers are likely to collect.\n"
    )


def build_reel_discovery_agent_task(
    *,
    search_config: ReelDiscoverySearchConfig | None = None,
    max_steps: int,
    agent_index: int,
    agent_count: int,
) -> AgentTask:
    return AgentTask(
        description=_discovery_worker_description(
            base_description=_build_reel_discovery_task(search_config),
            agent_index=agent_index,
            agent_count=agent_count,
        ),
        url=INSTAGRAM_REELS_FEED_URL,
        max_steps=max_steps,
        metadata={
            **build_instagram_reels_browser_use_metadata(),
            "discovery_agent_index": agent_index,
            "discovery_agent_count": agent_count,
        },
    )


def _build_browser_port_for_cdp(cdp_url: str) -> BrowserAutomationPort:
    provider = BrowserUseProvider(
        llm_model="ChatBrowserUse",
        dry_run=False,
        browser_config=BrowserUseBrowserConfig(cdp_url=cdp_url, headless=False, keep_alive=False),
    )
    return BrowserProviderFacade(provider)


@asynccontextmanager
async def _parallel_discovery_browsers(
    primary_browser: BrowserAutomationPort,
    *,
    browser_runtime_env: Mapping[str, str] | None,
    agent_count: int,
):
    if agent_count <= 1 or not _supports_parallel_local_windows(browser_runtime_env):
        yield [primary_browser for _ in range(agent_count)]
        return

    runtime_env = browser_runtime_env or {}
    browsers: list[BrowserAutomationPort] = []
    processes: list[Any] = []
    temp_roots: list[Path] = []

    reuse_primary_browser = bool(str(runtime_env.get(ENV_BROWSER_USE_CDP_URL) or "").strip())
    if reuse_primary_browser:
        browsers.append(primary_browser)

    source_user_data_dir = str(runtime_env[ENV_CHROME_USER_DATA_DIR]).strip()
    profile_directory = str(runtime_env[ENV_CHROME_PROFILE_DIRECTORY]).strip()
    chrome_path = str(runtime_env[ENV_CHROME_EXECUTABLE_PATH]).strip()
    next_port = _cdp_start_port(runtime_env) + (1 if reuse_primary_browser else 0)
    workers_to_launch = agent_count - len(browsers)

    try:
        for worker_index in range(workers_to_launch):
            temp_root = Path(tempfile.mkdtemp(prefix=f"reel-discovery-worker-{worker_index + 1}-"))
            temp_roots.append(temp_root)
            ensure_profile_clone(
                source_user_data_dir=source_user_data_dir,
                profile_directory=profile_directory,
                target_user_data_dir=temp_root,
                refresh=True,
            )
            cdp_port = _find_free_local_port(next_port)
            next_port = cdp_port + 1
            process, cdp_url = await launch_local_debug_chrome(
                cdp_port=cdp_port,
                user_data_dir=temp_root,
                profile_directory=profile_directory,
                start_url=INSTAGRAM_REELS_FEED_URL,
                chrome_path=chrome_path,
            )
            processes.append(process)
            browsers.append(_build_browser_port_for_cdp(cdp_url))
        yield browsers
    finally:
        for process in processes:
            try:
                process.terminate()
            except Exception:
                pass
        for temp_root in temp_roots:
            shutil.rmtree(temp_root, ignore_errors=True)


async def _run_discovery_agent(
    *,
    browser: BrowserAutomationPort,
    task: AgentTask,
) -> AgentResult:
    try:
        return await browser.run_task(task)
    except Exception as exc:
        return AgentResult(
            task_id=task.task_id,
            success=False,
            provider=ProviderType.BROWSER_USE,
            output={
                "worker_failure": True,
                "exception_type": type(exc).__name__,
            },
            error=f"{type(exc).__name__}: {exc}",
            dry_run=task.dry_run,
        )


def _merge_reel_metric(existing: ReelSurfaceMetrics, incoming: ReelSurfaceMetrics) -> ReelSurfaceMetrics:
    return existing.model_copy(
        update={
            "source_url": existing.source_url or incoming.source_url,
            "video_download_url": existing.video_download_url or incoming.video_download_url,
            "views": max(existing.views, incoming.views),
            "likes": max(existing.likes, incoming.likes),
            "comments": max(existing.comments, incoming.comments),
            "creator_handle": existing.creator_handle or incoming.creator_handle,
            "caption_text": existing.caption_text or incoming.caption_text,
            "is_ugc_candidate": True
            if existing.is_ugc_candidate is True or incoming.is_ugc_candidate is True
            else incoming.is_ugc_candidate if existing.is_ugc_candidate is None else existing.is_ugc_candidate,
            "ugc_reason": existing.ugc_reason or incoming.ugc_reason,
            "collected_at": max(existing.collected_at, incoming.collected_at),
        }
    )


def merge_discovered_reel_metrics(metrics: list[ReelSurfaceMetrics]) -> list[ReelSurfaceMetrics]:
    deduped: dict[str, ReelSurfaceMetrics] = {}
    for metric in metrics:
        key = metric.reel_id or metric.source_url
        if not key:
            continue
        existing = deduped.get(key)
        deduped[key] = metric if existing is None else _merge_reel_metric(existing, metric)
    return list(deduped.values())


async def run_parallel_reel_discovery(
    *,
    browser: BrowserAutomationPort,
    search_config: ReelDiscoverySearchConfig | None = None,
    max_steps: int,
    agent_count: int | None = None,
    metrics_parser: Callable[[AgentResult], list[ReelSurfaceMetrics]] | None = None,
    browser_runtime_env: Mapping[str, str] | None = None,
) -> tuple[list[ReelSurfaceMetrics], list[AgentResult]]:
    resolved_agent_count = _resolved_discovery_agent_count(agent_count)
    parser = metrics_parser or _parse_reels_from_agent
    tasks = [
        build_reel_discovery_agent_task(
            search_config=search_config,
            max_steps=max_steps,
            agent_index=index,
            agent_count=resolved_agent_count,
        )
        for index in range(resolved_agent_count)
    ]
    async with _parallel_discovery_browsers(
        browser,
        browser_runtime_env=browser_runtime_env,
        agent_count=resolved_agent_count,
    ) as browsers:
        results = await asyncio.gather(
            *(
                _run_discovery_agent(browser=worker_browser, task=task)
                for worker_browser, task in zip(browsers, tasks, strict=False)
            )
        )
    if results and all(not result.success for result in results):
        errors = "; ".join(result.error or f"task={result.task_id}" for result in results)
        msg = f"All reel discovery agents failed: {errors}"
        raise RuntimeError(msg)
    merged_metrics = merge_discovered_reel_metrics(
        [metric for result in results for metric in parser(result)]
    )
    return merged_metrics, results


def _parse_compact_count(value: Any) -> int:
    """Normalize Instagram-style counts such as 87.5K, 1.2M, or 4,905."""

    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return 0
    raw = value.strip().replace(",", "").upper()
    if not raw:
        return 0
    multiplier = 1
    if raw.endswith("K"):
        multiplier = 1_000
        raw = raw[:-1]
    elif raw.endswith("M"):
        multiplier = 1_000_000
        raw = raw[:-1]
    elif raw.endswith("B"):
        multiplier = 1_000_000_000
        raw = raw[:-1]
    try:
        return int(float(raw) * multiplier)
    except ValueError:
        return 0


def _raw_reels_payload(result: AgentResult) -> Any:
    out = result.output
    raw = out.get("reels_json") or out.get("reels")
    if raw is None:
        structured_output = out.get("structured_output")
        if isinstance(structured_output, dict):
            raw = structured_output.get("reels")
    if raw is None:
        final_result = out.get("final_result")
        if isinstance(final_result, str):
            parsed = _extract_json_payload(final_result)
            if isinstance(parsed, dict):
                raw = parsed.get("reels")
            elif isinstance(parsed, list):
                raw = parsed
    return raw


def _extract_json_payload(text: str) -> Any:
    """Best-effort JSON extraction for Browser Use responses that wrap JSON in prose."""

    decoder = json.JSONDecoder()
    stripped = text.strip()
    unescaped = text.replace('\\"', '"').replace("\\n", "\n").strip()
    for candidate in (stripped, text, unescaped):
        if not candidate:
            continue
        try:
            parsed, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            return parsed

    for candidate in (text, unescaped):
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "reels" in parsed:
                return parsed
            if isinstance(parsed, list):
                return parsed
    return None


def _is_probable_video_download_url(value: Any) -> bool:
    """Accept direct reel media URLs and reject obvious CSS/JS/image/audio assets."""

    if not isinstance(value, str):
        return False
    url = value.strip()
    if not url.startswith(("http://", "https://")):
        return False
    lowered = url.lower()
    parsed = urlparse(url)
    path = parsed.path.lower()

    if path.endswith((".css", ".js", ".woff", ".woff2", ".ttf", ".otf", ".svg", ".png", ".jpg", ".jpeg", ".webp")):
        return False
    if "mime=audio" in lowered or "mime_type=audio" in lowered or "/audio/" in path:
        return False
    if path.endswith(".mp4"):
        return True

    video_hints = (
        "mime=video",
        "mime_type=video",
        "video_versions",
        "/video/",
        "/reel_media/",
        "/clips/",
        "/v/t",
    )
    return any(hint in lowered for hint in video_hints)


def _build_reel_discovery_task(search_config: ReelDiscoverySearchConfig | None = None) -> str:
    """Return a scrolling-first Instagram discovery prompt for Browser Use."""

    config = search_config or ReelDiscoverySearchConfig()
    if config.discovery_mode == "feed_scroll":
        creator_focus = "; ".join(config.creator_focus_terms)
        return (
            "Open Instagram in a logged-in session and go directly to https://www.instagram.com/reels/. "
            "This is a hackathon demo, so keep discovery simple and reliable.\n\n"
            "Goal:\n"
            f"- Scroll through Reels until you find {config.target_good_reels} strong creator-style reels.\n"
            f"- Prefer reels that match these styles: {creator_focus}\n"
            "- Avoid meme pages, sports clips, celebrities, publishers, random entertainment reposts, "
            "and obvious non-creator content.\n\n"
            "Workflow:\n"
            "1. Start from Instagram Reels, not hashtag pages.\n"
            "2. Slowly scroll the feed and inspect one reel at a time.\n"
            "3. For each visible reel, decide if it is true UGC/creator content or not.\n"
            "4. NEVER leave instagram.com, NEVER use search engines, NEVER open downloader sites, "
            "and NEVER search for 'instagram reel downloader'. Do not download media in the browser.\n"
            "5. NEVER click creator profiles, NEVER open DMs, NEVER like/comment/share/save/follow, "
            "and NEVER open the More menu unless the task explicitly requires it. This task does not require it.\n"
            "6. This task is discovery only. Store reel metadata and the canonical Instagram source_url only. "
            "Downloading happens later through the API/downloader pipeline outside the browser.\n"
            "7. When a reel looks promising and meets the engagement requirement, extract:\n"
            "   - reel_id\n"
            "   - source_url\n"
            "   - views\n"
            "   - likes\n"
            "   - comments\n"
            "   - creator_handle\n"
            "   - caption_text\n"
            "   - is_ugc_candidate\n"
            "   - ugc_reason\n"
            "8. Count a reel as promising only if it looks like a real creator/product/storytelling reel, "
            "not a random viral clip.\n"
            "9. Use 0 when a metric is unavailable. Do not invent missing URLs or counts.\n"
            f"10. As soon as you have {config.target_good_reels} good unique reels, stop and return the result.\n"
            "11. Return JSON only in the exact form:\n"
            '{"reels":[{"reel_id":"...","source_url":"...","views":0,"likes":0,"comments":0,"creator_handle":"...","caption_text":"...","is_ugc_candidate":true,"ugc_reason":"..."}]}\n'
        )
    hashtags = ", ".join(f"#{tag}" for tag in config.hashtags)
    creator_focus = "; ".join(config.creator_focus_terms)
    return (
        "Open Instagram in a logged-in session and discover strong UGC creator reels. "
        "Stay inside instagram.com only and do not use external downloader websites or search engines.\n\n"
        "Discovery priority:\n"
        f"- Start from these hashtags: {hashtags}\n"
        f"- Prefer creator styles such as: {creator_focus}\n\n"
        "Workflow:\n"
        "1. For each hashtag, open https://www.instagram.com/explore/tags/<hashtag>/ "
        "and look for Reels or Reel-heavy posts.\n"
        f"2. On each hashtag surface, perform {config.hashtag_scroll_passes} slow scroll inspections.\n"
        "3. Harvest creator candidates from posts that look like true UGC: a real "
        "person on camera, product demonstration, "
        "testimonial, routine breakdown, founder-led storytelling, or creator voiceover.\n"
        "4. Avoid meme pages, sports clips, celebrities, publishers, obvious "
        "entertainment pages, and random viral repost content.\n"
        "5. Do not use DuckDuckGo, Google, Bing, or any downloader website. Do not try to obtain MP4/media URLs "
        "inside the browser. Discovery is metadata only.\n"
        f"6. Open up to {config.creator_candidates_to_open} promising creator "
        "profiles discovered from those hashtags.\n"
        "7. For each creator profile, inspect the Reels tab and prioritize reels "
        "with visible engagement plus creator-style "
        "product storytelling.\n"
        f"8. Open up to {config.reel_candidates_to_open} of the strongest candidate "
        "reels across those creator profiles and extract, when visible:\n"
        "   - reel_id\n"
        "   - source_url\n"
        "   - views\n"
        "   - likes\n"
        "   - comments\n"
        "   - creator_handle\n"
        "   - caption_text\n"
        "   - is_ugc_candidate\n"
        "   - ugc_reason\n"
        "9. Do not finish after inspecting only one creator or one reel. Keep "
        "exploring until you inspected multiple hashtag surfaces "
        "and multiple creator profiles, or until you collected at least 5 unique candidate reels.\n"
        "10. Prefer reels from mid-sized creators and creator accounts over large "
        "brands, news pages, or broad entertainment accounts.\n"
        "11. Return JSON only in the exact form:\n"
        '{"reels":[{"reel_id":"...","source_url":"...","views":0,"likes":0,"comments":0,"creator_handle":"...","caption_text":"...","is_ugc_candidate":true,"ugc_reason":"..."}]}\n'
        "12. If some fields are unavailable, keep the reel entry and use 0 for numeric fields and null for "
        "optional text fields instead of inventing values."
    )


def _parse_reels_from_agent(result: AgentResult) -> list[ReelSurfaceMetrics]:
    raw = _raw_reels_payload(result)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, dict):
        raw = raw.get("reels")
    if not isinstance(raw, list):
        return []
    rows: list[ReelSurfaceMetrics] = []
    for item in raw:
        if isinstance(item, dict):
            try:
                rows.append(
                    ReelSurfaceMetrics.model_validate(
                        {
                            "reel_id": item.get("reel_id") or "",
                            "source_url": item.get("source_url") or "",
                            "video_download_url": (
                                item.get("video_download_url")
                                if _is_probable_video_download_url(item.get("video_download_url"))
                                else None
                            ),
                            "views": _parse_compact_count(item.get("views")),
                            "likes": _parse_compact_count(item.get("likes")),
                            "comments": _parse_compact_count(item.get("comments")),
                            "creator_handle": item.get("creator_handle"),
                            "caption_text": item.get("caption_text"),
                            "is_ugc_candidate": item.get("is_ugc_candidate"),
                            "ugc_reason": item.get("ugc_reason"),
                        }
                    )
                )
            except Exception:
                continue
    return rows


class ReelDiscoveryPipeline:
    def __init__(
        self,
        *,
        browser: BrowserAutomationPort,
        video_understanding: VideoUnderstandingPort,
        templates: TemplateStorePort,
        reel_sink: ReelMetadataSinkPort,
        gemini: GeminiVideoAgentPort,
        thresholds: ReelDiscoveryThresholds | None = None,
        download_dir: Path | None = None,
        metrics_parser: Callable[[AgentResult], list[ReelSurfaceMetrics]] | None = None,
        seed_metrics_loader: Callable[[], list[ReelSurfaceMetrics]] | None = None,
        search_config: ReelDiscoverySearchConfig | None = None,
        browser_runtime_env: Mapping[str, str] | None = None,
    ) -> None:
        self._browser = browser
        self._video = video_understanding
        self._templates = templates
        self._sink = reel_sink
        self._gemini = gemini
        self._thresholds = thresholds or ReelDiscoveryThresholds()
        self._download_dir = download_dir or Path.cwd() / "data" / "reels"
        self._metrics_parser = metrics_parser or _parse_reels_from_agent
        self._seed_metrics_loader = seed_metrics_loader
        self._search_config = search_config or ReelDiscoverySearchConfig()
        self._browser_runtime_env = dict(browser_runtime_env or {})

    def _passes(self, m: ReelSurfaceMetrics) -> bool:
        t = self._thresholds
        if m.likes < t.min_likes or m.comments < t.min_comments:
            return False
        return m.views >= t.min_views or m.views == 0

    async def run_discovery_cycle(self) -> list[VideoTemplateRecord]:
        """
        Scroll reels via Browser Use, persist metrics, download passers, analyze, template with Gemini.
        When the agent returns no structured reels, a single dry-run metric is synthesized if output indicates dry_run.
        """
        metrics: list[ReelSurfaceMetrics] = []
        result: AgentResult | None = None
        if self._seed_metrics_loader is not None:
            metrics = self._seed_metrics_loader()

        if not metrics:
            metrics, results = await run_parallel_reel_discovery(
                browser=self._browser,
                search_config=self._search_config,
                max_steps=40,
                metrics_parser=self._metrics_parser,
                browser_runtime_env=self._browser_runtime_env,
            )
            result = next((item for item in results if item.success), results[0] if results else None)
        else:
            result = AgentResult(
                task_id=f"seed_{uuid.uuid4().hex[:12]}",
                success=True,
                provider=ProviderType.MOCK,
                output={"seed_metrics": len(metrics)},
                dry_run=True,
            )

        if result is None:
            msg = "Reel discovery did not produce an agent result."
            raise RuntimeError(msg)

        if not metrics and result.dry_run:
            metrics = [
                ReelSurfaceMetrics(
                    reel_id=f"dry_{uuid.uuid4().hex[:8]}",
                    source_url="https://www.instagram.com/reels/dry_run/",
                    video_download_url=None,
                    views=max(self._thresholds.min_views, 50_000),
                    likes=max(self._thresholds.min_likes, 2_000),
                    comments=max(self._thresholds.min_comments, 100),
                )
            ]
        self._sink.persist_reel_metrics(metrics)

        created: list[VideoTemplateRecord] = []
        for m in metrics:
            if not self._passes(m):
                continue
            local_path = await self._ensure_local_reel(m, result)
            structure = await self._video.analyze_reel_file(local_path, reel_id=m.reel_id)
            self._templates.save_structure(structure)
            disposition, reason, veo_prompt = await self._gemini.decide_template_disposition(
                structure,
                peer_templates=self._templates.list_templates(),
            )
            tpl = VideoTemplateRecord(
                template_id=new_id("tpl"),
                structure_record_id=structure.record_id,
                veo_prompt_draft=veo_prompt,
                disposition=disposition,
                disposition_reason=reason,
            )
            if disposition == TemplateDisposition.DISCARD:
                continue
            self._templates.save_template(tpl)
            created.append(tpl)
        return created

    async def _ensure_local_reel(self, m: ReelSurfaceMetrics, discovery_result: AgentResult) -> str:
        """Return a filesystem path to an MP4 for TwelveLabs."""

        self._download_dir.mkdir(parents=True, exist_ok=True)
        if m.video_download_url:
            return await self._download_from_media_url(m)
        if discovery_result.dry_run:
            placeholder = self._download_dir / f"{m.reel_id}.mp4"
            if not placeholder.exists():
                placeholder.write_bytes(b"")
            return str(placeholder)
        msg = (
            f"Reel {m.reel_id} has no downloadable media URL. Discovery is metadata-only; "
            "use the API/Instaloader download stage instead of Browser Use for reel media retrieval."
        )
        raise RuntimeError(msg)

    async def _download_from_media_url(self, m: ReelSurfaceMetrics) -> str:
        """Download a reel directly from a media URL returned by the discovery agent."""

        if not m.video_download_url:
            msg = "video_download_url is required for direct media download."
            raise RuntimeError(msg)
        if not _is_probable_video_download_url(m.video_download_url):
            msg = f"video_download_url is not a direct video asset: {m.video_download_url}"
            raise RuntimeError(msg)

        target = self._download_dir / f"{m.reel_id}.mp4"
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            response = await client.get(m.video_download_url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and not (
                content_type.startswith("video/") or content_type.startswith("application/octet-stream")
            ):
                msg = f"Downloaded reel asset is not video content: {content_type}"
                raise RuntimeError(msg)
            target.write_bytes(response.content)
        return str(target)
