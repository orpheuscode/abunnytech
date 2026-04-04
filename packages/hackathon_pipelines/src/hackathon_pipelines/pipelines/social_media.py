"""Social posting and analytics via Browser Use; closes the loop back to template labels."""

from __future__ import annotations

import json
import uuid

from browser_runtime.types import AgentResult, AgentTask

from hackathon_pipelines.contracts import PostAnalyticsSnapshot, PostJob, TemplatePerformanceLabel, VideoTemplateRecord
from hackathon_pipelines.ports import AnalyticsSinkPort, BrowserAutomationPort, TemplateStorePort


def _parse_analytics(result: AgentResult) -> PostAnalyticsSnapshot | None:
    out = result.output
    raw = out.get("analytics_json") or out.get("analytics")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    return PostAnalyticsSnapshot(
        snapshot_id=f"snap_{uuid.uuid4().hex[:10]}",
        post_id=str(raw.get("post_id", "unknown")),
        views=int(raw.get("views", 0)),
        likes=int(raw.get("likes", 0)),
        comments=int(raw.get("comments", 0)),
        engagement_trend=raw.get("engagement_trend"),
    )


class SocialMediaPipeline:
    def __init__(
        self,
        *,
        browser: BrowserAutomationPort,
        analytics_sink: AnalyticsSinkPort,
        templates: TemplateStorePort,
    ) -> None:
        self._browser = browser
        self._analytics = analytics_sink
        self._templates = templates

    async def publish_reel(self, job: PostJob) -> AgentResult:
        caption = job.caption.replace('"', '\\"')
        task = AgentTask(
            description=(
                f"On instagram.com (logged in), create a new Reel post using the video file at {job.media_path}. "
                f'Set caption to "{caption}". Publish. Respond with JSON '
                '{"post_id":"...","post_url":"..."}'
            ),
            max_steps=35,
            dry_run=job.dry_run,
            metadata={"pipeline": "social_publish", "job_id": job.job_id},
        )
        return await self._browser.run_task(task)

    async def fetch_post_analytics(self, post_id: str, *, dry_run: bool = True) -> PostAnalyticsSnapshot:
        task = AgentTask(
            description=(
                f"Open Instagram insights for post {post_id}. Read views, likes, comments, and short trend note. "
                'Respond JSON only: {"post_id":"...","views":0,"likes":0,"comments":0,"engagement_trend":"..."}'
            ),
            max_steps=25,
            dry_run=dry_run,
            metadata={"post_id": post_id},
        )
        result = await self._browser.run_task(task)
        snap = _parse_analytics(result)
        if snap:
            self._analytics.persist_post_analytics(snap)
            return snap
        fallback = PostAnalyticsSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:10]}",
            post_id=post_id,
            views=10_000 if result.dry_run else 0,
            likes=400 if result.dry_run else 0,
            comments=40 if result.dry_run else 0,
            engagement_trend="dry_run_flat" if result.dry_run else None,
        )
        self._analytics.persist_post_analytics(fallback)
        return fallback

    def apply_performance_to_template(
        self,
        template: VideoTemplateRecord,
        snapshot: PostAnalyticsSnapshot,
        *,
        strong_views: int = 50_000,
        weak_views: int = 2_000,
    ) -> VideoTemplateRecord:
        if snapshot.views >= strong_views and snapshot.likes >= max(500, snapshot.views // 200):
            label = TemplatePerformanceLabel.SUCCESSFUL_REUSE
        elif snapshot.views >= weak_views:
            label = TemplatePerformanceLabel.REMIXABLE
        else:
            label = TemplatePerformanceLabel.WEAK_DISCARD
        updated = template.model_copy(update={"performance_label": label})
        self._templates.update_template(updated)
        return updated
