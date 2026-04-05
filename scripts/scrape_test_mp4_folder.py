# ruff: noqa: E402

from __future__ import annotations

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

VIDEO_DIR = ROOT / "data" / "test mp4"
DB_PATH = ROOT / "data" / "test_mp4_video_structures.sqlite3"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


async def main() -> None:
    load_env(ROOT / ".env")
    apply_to_environ(read_for_subprocess())

    result = await seed_video_structure_db_from_local_folder(
        video_dir=VIDEO_DIR,
        db_path=DB_PATH,
        video_understanding=TwelveLabsUnderstanding(dry_run=False),
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
