"""Reel discovery: Browser Use → threshold → download → TwelveLabs → DB → Gemini template decision."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from browser_runtime.types import AgentResult, AgentTask, ProviderType
from pydantic import BaseModel, ConfigDict, Field

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


class ReelDiscoverySearchConfig(BaseModel):
    """Controls how Instagram discovery should target creator-style content."""

    model_config = ConfigDict(extra="forbid")

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
        final_result = out.get("final_result")
        if isinstance(final_result, str):
            try:
                parsed = json.loads(final_result)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                raw = parsed.get("reels")
            elif isinstance(parsed, list):
                raw = parsed
    return raw


def _build_reel_discovery_task(search_config: ReelDiscoverySearchConfig | None = None) -> str:
    """Return a scrolling-first Instagram discovery prompt for Browser Use."""

    config = search_config or ReelDiscoverySearchConfig()
    hashtags = ", ".join(f"#{tag}" for tag in config.hashtags)
    creator_focus = "; ".join(config.creator_focus_terms)
    return (
        "Open Instagram in a logged-in session and discover strong UGC creator reels. "
        "Do not rely on random generic Reels feed content when hashtag surfaces can "
        "guide you to creator-style content.\n\n"
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
        f"5. Open up to {config.creator_candidates_to_open} promising creator "
        "profiles discovered from those hashtags.\n"
        "6. For each creator profile, inspect the Reels tab and prioritize reels "
        "with visible engagement plus creator-style "
        "product storytelling.\n"
        f"7. Open up to {config.reel_candidates_to_open} of the strongest candidate "
        "reels across those creator profiles and extract, when visible:\n"
        "   - reel_id\n"
        "   - source_url\n"
        "   - video_download_url\n"
        "   - views\n"
        "   - likes\n"
        "   - comments\n"
        "8. The video_download_url must be a direct downloadable media URL for the reel video whenever available.\n"
        "9. Do not finish after inspecting only one creator or one reel. Keep "
        "exploring until you inspected multiple hashtag surfaces "
        "and multiple creator profiles, or until you collected at least 5 unique candidate reels.\n"
        "10. Prefer reels from mid-sized creators and creator accounts over large "
        "brands, news pages, or broad entertainment accounts.\n"
        "11. Return JSON only in the exact form:\n"
        '{"reels":[{"reel_id":"...","source_url":"...","video_download_url":"https://...mp4","views":0,"likes":0,"comments":0}]}\n'
        "12. If some fields are unavailable, keep the reel entry and use 0 for numeric fields and null for "
        "video_download_url instead of inventing values."
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
                            "video_download_url": item.get("video_download_url"),
                            "views": _parse_compact_count(item.get("views")),
                            "likes": _parse_compact_count(item.get("likes")),
                            "comments": _parse_compact_count(item.get("comments")),
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
            task = AgentTask(
                description=_build_reel_discovery_task(self._search_config),
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
                            "Start from UGC-oriented hashtag surfaces, gather creator "
                            "candidates, then inspect creator reels. "
                            "Prefer creator-style product demos and testimonials over generic viral clips. "
                            "You must inspect the visible feed, scroll, and continue gathering unique reels "
                            "before using done. When the page appears blank, treat it as a loading or SPA state "
                            "and recover by waiting or revisiting the Reels route."
                        ),
                    },
                },
            )
            result = await self._browser.run_task(task)
            metrics = self._metrics_parser(result)
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
        artifacts = discovery_result.artifacts
        if artifacts:
            return artifacts[0]
        if m.video_download_url:
            return await self._download_from_media_url(m)
        if discovery_result.dry_run:
            placeholder = self._download_dir / f"{m.reel_id}.mp4"
            if not placeholder.exists():
                placeholder.write_bytes(b"")
            return str(placeholder)
        dl = AgentTask(
            description=(
                f"Download the Instagram reel {m.reel_id} from {m.source_url} to a local mp4 under "
                f'{self._download_dir!s}. Return JSON {{"path":"absolute path"}}.'
            ),
            max_steps=25,
            metadata={"reel_id": m.reel_id},
        )
        dl_result = await self._browser.run_task(dl)
        path = dl_result.output.get("path") or (dl_result.artifacts[0] if dl_result.artifacts else None)
        if not path:
            msg = "Browser agent did not return a downloaded reel path"
            raise RuntimeError(msg)
        return str(path)

    async def _download_from_media_url(self, m: ReelSurfaceMetrics) -> str:
        """Download a reel directly from a media URL returned by the discovery agent."""

        if not m.video_download_url:
            msg = "video_download_url is required for direct media download."
            raise RuntimeError(msg)

        target = self._download_dir / f"{m.reel_id}.mp4"
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            response = await client.get(m.video_download_url)
            response.raise_for_status()
            target.write_bytes(response.content)
        return str(target)
