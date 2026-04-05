# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "hackathon_pipelines" / "src"))

from hackathon_pipelines.adapters.live_api import TwelveLabsUnderstanding
from hackathon_pipelines.local_video_structure_db import seed_video_structure_db_from_local_folder

from runtime_dashboard.secrets_store import apply_to_environ, read_for_subprocess

DEFAULT_VIDEO_DIR = ROOT / "data" / "test mp4"
DEFAULT_DB_PATH = ROOT / "data" / "local_video_structures.sqlite3"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-dir", type=Path, default=DEFAULT_VIDEO_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--selected-video",
        default=os.getenv("PRESELECTED_UGC_VIDEO", ""),
        help="Optional file name in the source folder to mark as the selected UGC seed and process first.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Bypass live TwelveLabs calls and emit dry-run data.")
    return parser.parse_args()


async def main() -> None:
    load_env(ROOT / ".env")
    apply_to_environ(read_for_subprocess())
    args = parse_args()
    selected_video = str(args.selected_video).strip() or None

    if not args.dry_run and not (
        os.getenv("TWELVE_LABS_API_KEY", "").strip() or os.getenv("TWELVELABS_API_KEY", "").strip()
    ):
        msg = "TWELVE_LABS_API_KEY or TWELVELABS_API_KEY must be set unless --dry-run is used."
        raise RuntimeError(msg)

    result = await seed_video_structure_db_from_local_folder(
        video_dir=args.video_dir,
        db_path=args.db_path,
        video_understanding=TwelveLabsUnderstanding(dry_run=args.dry_run),
        selected_video_name=selected_video,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
