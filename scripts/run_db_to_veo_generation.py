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

from hackathon_pipelines.adapters.live_api import GeminiTemplateAgent, VeoVideoGenerator
from hackathon_pipelines.pipelines.db_to_video_generation import (
    generate_video_from_best_db_template,
)
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore

DEFAULT_DB_PATH = ROOT / "data" / "instagram_reel_queue_twelvelabs_probe.sqlite3"
DEFAULT_AVATAR_IMAGE_PATH = ROOT / "test_avatar" / "IMG20260329212538.jpg"
DEFAULT_PRODUCT_IMAGE_PATH = ROOT / "test_product" / "camera.jpg"


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

    db_path = Path(os.getenv("GENERATION_DB_PATH", DEFAULT_DB_PATH))
    avatar_image_path = Path(os.getenv("AVATAR_IMAGE_PATH", DEFAULT_AVATAR_IMAGE_PATH))
    product_image_path = Path(os.getenv("PRODUCT_IMAGE_PATH", DEFAULT_PRODUCT_IMAGE_PATH))
    product_title = os.getenv("PRODUCT_TITLE") or None
    product_description = os.getenv("PRODUCT_DESCRIPTION") or None
    gemini_dry_run = os.getenv("GEMINI_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}
    veo_dry_run = os.getenv("VEO_DRY_RUN", "1").strip().lower() in {"1", "true", "yes"}

    store = SQLiteHackathonStore(db_path)
    gemini = GeminiTemplateAgent(dry_run=gemini_dry_run)
    veo = VeoVideoGenerator(dry_run=veo_dry_run)

    result = await generate_video_from_best_db_template(
        store,
        gemini=gemini,
        veo=veo,
        product_image_path=str(product_image_path),
        avatar_image_path=str(avatar_image_path),
        product_title=product_title,
        product_description=product_description,
    )

    report = {
        "db_path": str(db_path),
        "avatar_image_path": str(avatar_image_path),
        "product_image_path": str(product_image_path),
        "gemini_dry_run": gemini_dry_run,
        "veo_dry_run": veo_dry_run,
        "templates_created": result.templates_created,
        "selected_template": result.template.model_dump(mode="json"),
        "product": result.product.model_dump(mode="json"),
        "bundle": result.bundle.model_dump(mode="json"),
        "generation_config": result.bundle.generation_config.model_dump(mode="json"),
        "prompt_artifacts": {
            "artifact_dir": result.bundle.prompt_package.artifact_dir,
            "system_prompt_path": result.bundle.prompt_package.system_prompt_path,
            "user_prompt_path": result.bundle.prompt_package.user_prompt_path,
            "full_prompt_path": result.bundle.prompt_package.full_prompt_path,
        },
        "artifact": result.artifact.model_dump(mode="json"),
        "stored_templates_count": len(store.list_templates()),
        "stored_structures_count": len(store.list_structures()),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
