from __future__ import annotations

import uuid
from typing import Any


def register_visual_assets(
    *,
    matrix_id: str,
    dry_run: bool,
    collection_hint: str | None,
    visual_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Nano Banana asset registration (stub).

    Returns manifest rows to merge into asset_manifest.json. Live mode would
    register blobs with NANO_BANANA_* configuration; dry-run emits realistic stubs.
    """
    collection = collection_hint or f"nb_dry_{matrix_id}_{uuid.uuid4().hex[:8]}"
    base = {
        "kind": "style_pack",
        "provider": "nano_banana",
        "collection_id": collection,
        "status": "stub" if dry_run else "pending",
        "metadata": {"visual_summary": visual_summary},
    }
    rows = [
        base,
        {
            "kind": "reference_still",
            "provider": "nano_banana",
            "asset_uri": f"fixture://nano-banana/{collection}/hero_still",
            "status": "stub" if dry_run else "pending",
            "metadata": {},
        },
    ]
    return rows
