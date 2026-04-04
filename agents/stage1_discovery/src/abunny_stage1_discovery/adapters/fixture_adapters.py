from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pipeline_contracts.models import CompetitorWatchItem, TrendingAudioItem

from abunny_stage1_discovery.analysis_enums import CtaKind, HookLabel, ProductIntegration
from abunny_stage1_discovery.models import (
    AccountMetadata,
    AnalyzedCandidate,
    DiscoveryPlan,
    MediaDownloadJob,
    OverlayCutPoint,
    RawShortCandidate,
    TranscriptSegment,
)


def load_fixture_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class FixtureShortFormDiscovery:
    """Reads `discovered_items.json` from a fixture directory."""

    def __init__(self, fixture_dir: Path) -> None:
        self._fixture_dir = fixture_dir
        data = load_fixture_json(fixture_dir / "discovered_items.json")
        items = data.get("items", [])
        self._items: list[dict[str, Any]] = items if isinstance(items, list) else []

    def discover_short_form(self, plan: DiscoveryPlan) -> list[RawShortCandidate]:
        out: list[RawShortCandidate] = []
        platforms = set(plan.platforms) if plan.platforms else None
        for row in self._items:
            if len(out) >= plan.max_candidates:
                break
            plat = str(row.get("platform", "tiktok"))
            if platforms and plat not in platforms:
                continue
            out.append(
                RawShortCandidate(
                    candidate_id=str(row["candidate_id"]),
                    source_url=str(row["source_url"]),
                    platform=plat,
                    title=row.get("title"),
                    creator_handle=row.get("creator_handle"),
                    thumbnail_url=row.get("thumbnail_url"),
                    content_tier=str(row.get("content_tier", "standard")),
                )
            )
        return out


class FixtureAccountMetadata:
    def __init__(self, fixture_dir: Path) -> None:
        path = fixture_dir / "accounts.json"
        if not path.exists():
            self._by_key: dict[str, dict[str, Any]] = {}
            return
        data = load_fixture_json(path)
        self._by_key = {str(k): v for k, v in data.items()} if isinstance(data, dict) else {}

    def extract_account_metadata(self, handle: str, platform: str) -> AccountMetadata | None:
        key = f"{handle}|{platform}"
        row = self._by_key.get(key)
        if not row:
            return AccountMetadata(handle=handle, platform=platform, display_name=handle)
        return AccountMetadata(
            handle=handle,
            platform=platform,
            display_name=row.get("display_name"),
            follower_count_approx=row.get("follower_count_approx"),
            bio=row.get("bio"),
        )


class FixtureMediaDownloadPlanner:
    def plan_media_downloads(self, candidates: list[RawShortCandidate]) -> list[MediaDownloadJob]:
        jobs: list[MediaDownloadJob] = []
        for i, c in enumerate(candidates):
            jobs.append(
                MediaDownloadJob(
                    job_id=f"dl_{uuid.uuid4().hex[:8]}",
                    candidate_id=c.candidate_id,
                    source_url=c.source_url,
                    priority=100 - i,
                    asset_kind="video",
                )
            )
        return jobs


class FixtureAnalysisPipeline:
    """TwelveLabs/Gemini stand-in: loads per-candidate analysis from `analysis.json`."""

    def __init__(self, fixture_dir: Path) -> None:
        path = fixture_dir / "analysis.json"
        self._by_id: dict[str, dict[str, Any]] = {}
        if path.exists():
            data = load_fixture_json(path)
            if isinstance(data, dict):
                self._by_id = {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def analyze(self, candidate: RawShortCandidate, jobs: list[MediaDownloadJob]) -> AnalyzedCandidate:
        _ = jobs
        payload = self._by_id.get(candidate.candidate_id, {})
        segments = [
            TranscriptSegment(
                start_seconds=float(s["start_seconds"]),
                end_seconds=float(s["end_seconds"]),
                text=str(s["text"]),
            )
            for s in payload.get("transcript", [])
            if isinstance(s, dict) and "text" in s
        ]
        if not segments and candidate.title:
            segments = [
                TranscriptSegment(start_seconds=0.0, end_seconds=2.0, text=candidate.title),
            ]

        hook_raw = str(payload.get("hook_label", HookLabel.UNKNOWN.value))
        try:
            hook_label = HookLabel(hook_raw).value
        except ValueError:
            hook_label = HookLabel.UNKNOWN.value

        cuts = [
            OverlayCutPoint(t_seconds=float(c["t_seconds"]), kind=str(c.get("kind", "beat")))
            for c in payload.get("overlay_cut_points", [])
            if isinstance(c, dict) and "t_seconds" in c
        ]

        cta_raw = str(payload.get("cta_kind", CtaKind.NONE.value))
        try:
            cta_kind = CtaKind(cta_raw).value
        except ValueError:
            cta_kind = CtaKind.NONE.value

        prod_raw = str(payload.get("product_integration", ProductIntegration.NONE.value))
        try:
            product_integration = ProductIntegration(prod_raw).value
        except ValueError:
            product_integration = ProductIntegration.NONE.value

        return AnalyzedCandidate(
            raw=candidate,
            transcript=segments,
            hook_label=hook_label,
            overlay_cut_points=cuts,
            cta_kind=cta_kind,
            product_integration=product_integration,
        )


class FixtureResearchCatalog:
    """Loads `trending_audio.json` and `competitors.json` for handoff artifacts."""

    def __init__(self, fixture_dir: Path) -> None:
        self._fixture_dir = fixture_dir

    def load_trending_audio(self) -> list[TrendingAudioItem]:
        path = self._fixture_dir / "trending_audio.json"
        if not path.exists():
            return []
        data = load_fixture_json(path)
        items = data if isinstance(data, list) else data.get("items", [])
        return [TrendingAudioItem.model_validate(x) for x in items]

    def load_competitors(self) -> list[CompetitorWatchItem]:
        path = self._fixture_dir / "competitors.json"
        if not path.exists():
            return []
        data = load_fixture_json(path)
        items = data if isinstance(data, list) else data.get("items", [])
        return [CompetitorWatchItem.model_validate(x) for x in items]
