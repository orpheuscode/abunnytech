# ruff: noqa: E402

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "hackathon_pipelines" / "src"))

from hackathon_pipelines.adapters.instagram_download_api import InstagramDownloadAPI
from hackathon_pipelines.adapters.instagram_instaloader import InstagramInstaloaderDownloader
from hackathon_pipelines.adapters.live_api import TwelveLabsUnderstanding
from hackathon_pipelines.contracts import ReelSurfaceMetrics
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

QUEUE_DB_PATH = Path(os.getenv("REEL_QUEUE_DB_PATH", ROOT / "data" / "instagram_reel_queue_attempt_1.sqlite3"))
TEMP_VIDEO_DIR = Path(os.getenv("REEL_TEMP_VIDEO_DIR", ROOT / "data" / "tmp_reels_instaloader"))
KEEP_TEMP_FILES = os.getenv("KEEP_TEMP_REEL_FILES", "").strip().lower() in {"1", "true", "yes"}
DRY_RUN_TWELVELABS = os.getenv("DRY_RUN_TWELVELABS", "").strip().lower() in {"1", "true", "yes"}
DOWNLOAD_BACKEND = os.getenv("INSTAGRAM_DOWNLOAD_BACKEND", "instaloader").strip().lower() or "instaloader"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _already_processed_reel_ids(store: SQLiteHackathonStore) -> set[str]:
    return {record.source_reel_id for record in store.list_structures()}


async def _download_media_url_to_path(media_url: str, reel_id: str) -> Path:
    TEMP_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    target = TEMP_VIDEO_DIR / f"{reel_id}.mp4"
    async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
        response = await client.get(media_url)
        response.raise_for_status()
        target.write_bytes(response.content)
    return target


def _build_downloader() -> object:
    if DOWNLOAD_BACKEND == "instaloader":
        return InstagramInstaloaderDownloader()
    if DOWNLOAD_BACKEND == "api":
        return InstagramDownloadAPI()
    msg = f"Unsupported INSTAGRAM_DOWNLOAD_BACKEND={DOWNLOAD_BACKEND!r}"
    raise RuntimeError(msg)


async def _download_reel_to_temp_path(
    *,
    downloader: object,
    reel: ReelSurfaceMetrics,
) -> tuple[Path, ReelSurfaceMetrics, dict[str, object]]:
    if DOWNLOAD_BACKEND == "instaloader":
        instaloader_downloader = downloader
        download = await instaloader_downloader.download_reel(source_url=reel.source_url, reel_id=reel.reel_id)
        likes = reel.likes if download.likes is None else int(download.likes)
        comments = reel.comments if download.comments is None else int(download.comments)
        updated_reel = reel.model_copy(
            update={
                "video_download_url": download.media_url or reel.video_download_url,
                "creator_handle": download.creator_handle or reel.creator_handle,
                "caption_text": download.caption_text or reel.caption_text,
                "likes": likes,
                "comments": comments,
            }
        )
        download_info = download.model_dump(mode="json")
        return Path(download.local_video_path), updated_reel, download_info

    api_downloader = downloader
    download = await api_downloader.resolve_media_url(source_url=reel.source_url, reel_id=reel.reel_id)
    temp_path = await _download_media_url_to_path(download.media_url, reel.reel_id)
    updated_reel = reel.model_copy(update={"video_download_url": download.media_url})
    return temp_path, updated_reel, {
        "reel_id": reel.reel_id,
        "source_url": reel.source_url,
        "media_url": download.media_url,
        "local_video_path": str(temp_path),
    }


async def main() -> None:
    load_env(ROOT / ".env")

    store = SQLiteHackathonStore(QUEUE_DB_PATH)
    downloader = _build_downloader()
    video_understanding = TwelveLabsUnderstanding(dry_run=DRY_RUN_TWELVELABS)

    queued_reels = store.list_reel_metrics()
    processed_reel_ids = _already_processed_reel_ids(store)
    pending_reels = [reel for reel in queued_reels if reel.reel_id not in processed_reel_ids]

    processed: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for reel in pending_reels:
        temp_path: Path | None = None
        try:
            temp_path, updated_reel, download_info = await _download_reel_to_temp_path(downloader=downloader, reel=reel)
            store.upsert_reel_metrics([updated_reel])
            structure = await video_understanding.analyze_reel_file(str(temp_path), reel_id=reel.reel_id)
            store.save_structure(structure)
            processed.append(
                {
                    "reel_id": reel.reel_id,
                    "source_url": reel.source_url,
                    "media_url": updated_reel.video_download_url,
                    "temp_video_path": str(temp_path),
                    "structure_record_id": structure.record_id,
                    "download_backend": DOWNLOAD_BACKEND,
                    "download_info": download_info,
                }
            )
        except Exception as exc:
            errors.append({"reel_id": reel.reel_id, "error": f"{type(exc).__name__}: {exc}"})
        finally:
            if temp_path is not None and not KEEP_TEMP_FILES:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    if temp_path.parent != TEMP_VIDEO_DIR:
                        temp_path.parent.rmdir()
                except Exception:
                    pass

    report = {
        "queue_db_path": str(QUEUE_DB_PATH),
        "queued_reels_count": len(queued_reels),
        "pending_reels_count": len(pending_reels),
        "processed_count": len(processed),
        "processed": processed,
        "errors": errors,
        "stored_structures_count": len(store.list_structures()),
        "dry_run_twelvelabs": DRY_RUN_TWELVELABS,
        "download_backend": DOWNLOAD_BACKEND,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
