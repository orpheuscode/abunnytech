"""Seed the hackathon SQLite store from local MP4 files."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hackathon_pipelines.contracts import ReelSurfaceMetrics
from hackathon_pipelines.ports import VideoUnderstandingPort
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore


def _slugify_path(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return normalized or "video"


def _ordered_video_paths(video_dir: Path, *, selected_video_name: str | None = None) -> list[Path]:
    paths = sorted(path for path in video_dir.glob("*.mp4") if path.is_file())
    if not paths:
        return []
    if not selected_video_name:
        return paths

    selected_path = video_dir / selected_video_name
    if not selected_path.exists():
        msg = f"Selected video {selected_video_name!r} was not found in {video_dir}"
        raise FileNotFoundError(msg)

    return [selected_path, *[path for path in paths if path != selected_path]]


def _local_reel_id(path: Path, *, video_dir: Path) -> str:
    relative = path.relative_to(video_dir)
    return f"local_{_slugify_path(relative.as_posix())}"


def _metric_for_local_video(
    path: Path,
    *,
    video_dir: Path,
    is_selected_ugc: bool,
) -> ReelSurfaceMetrics:
    reel_id = _local_reel_id(path, video_dir=video_dir)
    return ReelSurfaceMetrics(
        reel_id=reel_id,
        source_url=path.resolve().as_uri(),
        creator_handle="@local_seed",
        caption_text=path.stem.replace("_", " "),
        is_ugc_candidate=is_selected_ugc,
        ugc_reason="preselected_local_seed" if is_selected_ugc else None,
    )


class LocalVideoStructureSeedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db_path: str
    video_dir: str
    selected_video_name: str | None = None
    discovered_video_count: int = 0
    processed_reel_ids: list[str] = Field(default_factory=list)
    skipped_reel_ids: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    halted_due_to_rate_limit: bool = False
    resume_after: str | None = None
    stored_structures_count: int = 0


def _extract_rate_limit_resume_after(message: str) -> str | None:
    match = re.search(r"after\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)", message)
    if match:
        return match.group(1)
    return None


def _is_rate_limit_error(exc: Exception) -> tuple[bool, str | None]:
    message = f"{type(exc).__name__}: {exc}"
    if "TooManyRequestsError" not in message and "status_code: 429" not in message:
        return False, None
    return True, _extract_rate_limit_resume_after(message)


async def seed_video_structure_db_from_local_folder(
    *,
    video_dir: str | Path,
    db_path: str | Path,
    video_understanding: VideoUnderstandingPort,
    selected_video_name: str | None = None,
) -> LocalVideoStructureSeedResult:
    resolved_video_dir = Path(video_dir)
    if not resolved_video_dir.exists():
        raise FileNotFoundError(resolved_video_dir)
    if not resolved_video_dir.is_dir():
        msg = f"Expected a directory of MP4 files, got {resolved_video_dir}"
        raise NotADirectoryError(msg)

    ordered_paths = _ordered_video_paths(resolved_video_dir, selected_video_name=selected_video_name)
    effective_selected_video_name = selected_video_name or (ordered_paths[0].name if ordered_paths else None)
    store = SQLiteHackathonStore(db_path)
    existing_reel_ids = {record.source_reel_id for record in store.list_structures()}

    metrics = [
        _metric_for_local_video(
            path,
            video_dir=resolved_video_dir,
            is_selected_ugc=effective_selected_video_name is not None and path.name == effective_selected_video_name,
        )
        for path in ordered_paths
    ]
    if metrics:
        store.upsert_reel_metrics(metrics)

    processed_reel_ids: list[str] = []
    skipped_reel_ids: list[str] = []
    error_messages: list[str] = []
    halted_due_to_rate_limit = False
    resume_after: str | None = None
    for metric, path in zip(metrics, ordered_paths, strict=True):
        if metric.reel_id in existing_reel_ids:
            skipped_reel_ids.append(metric.reel_id)
            continue
        try:
            structure = await video_understanding.analyze_reel_file(str(path), reel_id=metric.reel_id)
        except Exception as exc:
            is_rate_limited, parsed_resume_after = _is_rate_limit_error(exc)
            if is_rate_limited:
                halted_due_to_rate_limit = True
                resume_after = parsed_resume_after
                details = f"{metric.reel_id}: {type(exc).__name__}: {exc}"
                if resume_after is not None:
                    reset_at = datetime.fromisoformat(resume_after.replace("Z", "+00:00")).astimezone(UTC)
                    details = f"{details} Resume after {reset_at.isoformat().replace('+00:00', 'Z')}."
                error_messages.append(details)
                break
            error_messages.append(f"{metric.reel_id}: {type(exc).__name__}: {exc}")
            continue
        store.save_structure(structure)
        processed_reel_ids.append(metric.reel_id)

    return LocalVideoStructureSeedResult(
        db_path=str(Path(db_path)),
        video_dir=str(resolved_video_dir),
        selected_video_name=effective_selected_video_name,
        discovered_video_count=len(ordered_paths),
        processed_reel_ids=processed_reel_ids,
        skipped_reel_ids=skipped_reel_ids,
        error_messages=error_messages,
        halted_due_to_rate_limit=halted_due_to_rate_limit,
        resume_after=resume_after,
        stored_structures_count=len(store.list_structures()),
    )
