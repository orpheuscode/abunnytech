"""Reel discovery: Browser Use → threshold → download → TwelveLabs → DB → Gemini template decision."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path

from browser_runtime.types import AgentResult, AgentTask, ProviderType

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


def _parse_reels_from_agent(result: AgentResult) -> list[ReelSurfaceMetrics]:
    out = result.output
    raw = out.get("reels_json") or out.get("reels")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    rows: list[ReelSurfaceMetrics] = []
    for item in raw:
        if isinstance(item, dict):
            rows.append(ReelSurfaceMetrics.model_validate(item))
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

    def _passes(self, m: ReelSurfaceMetrics) -> bool:
        t = self._thresholds
        return m.views >= t.min_views and m.likes >= t.min_likes and m.comments >= t.min_comments

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
                description=(
                    "Open Instagram Reels in a logged-in session. Scroll, and for each visible reel record: "
                    "reel_id, source_url, views, likes, comments. When finished, respond with JSON only in the form "
                    '{"reels":[{"reel_id":"...","source_url":"...","views":0,"likes":0,"comments":0}]}'
                ),
                max_steps=40,
                metadata={"pipeline": "reel_discovery"},
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
