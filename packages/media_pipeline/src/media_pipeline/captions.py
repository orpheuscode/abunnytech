from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from media_pipeline.models import AdaptedScript
from pipeline_contracts.models import IdentityMatrix, VideoBlueprint


class CaptionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: str = Field(..., description="Final caption body for the primary variant.")
    hashtags: list[str] = Field(default_factory=list)
    title_for_upload: str | None = None
    alt_text: str | None = Field(default=None, description="Accessibility / alt where supported.")


def _normalize_hashtags(raw: list[str], persona_topics: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for h in raw:
        t = h.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = f"#{t.lstrip('#')}"
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    for topic in persona_topics:
        slug = re.sub(r"[^a-zA-Z0-9]+", "", topic)[:30]
        if slug and f"#{slug.lower()}" not in seen:
            out.append(f"#{slug}")
            seen.add(f"#{slug.lower()}")
    return out[:12]


def build_caption_metadata(
    blueprint: VideoBlueprint,
    identity: IdentityMatrix,
    script: AdaptedScript,
) -> CaptionMetadata:
    """
    Produce caption, hashtags, and short metadata from blueprint + identity + adapted script.

    Respects blueprint suggested caption when present; augments with persona disclosure.
    """
    base = (blueprint.suggested_caption or "").strip()
    if not base:
        base = f"{blueprint.title.strip()}\n\n{script.segments[0].text if script.segments else blueprint.hook}"

    disclosure = identity.persona.disclosure_line
    if disclosure and disclosure not in base:
        base = f"{base}\n\n{disclosure}".strip()

    hashtags = _normalize_hashtags(
        list(blueprint.hashtags),
        identity.persona.topics,
    )

    hook_preview = script.segments[0].text[:120] if script.segments else blueprint.hook[:120]
    alt_text = f"{identity.display_name}: {hook_preview}"

    return CaptionMetadata(
        caption=base,
        hashtags=hashtags,
        title_for_upload=blueprint.title.strip() or identity.display_name,
        alt_text=alt_text,
    )
