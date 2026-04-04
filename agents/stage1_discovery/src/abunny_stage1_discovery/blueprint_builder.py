from __future__ import annotations

import uuid

from pipeline_contracts.models import IdentityMatrix, VideoBlueprint

from abunny_stage1_discovery.models import AnalyzedCandidate


def build_video_blueprint(
    analyzed: AnalyzedCandidate,
    identity: IdentityMatrix,
    *,
    audio_id: str | None = None,
    blueprint_id: str | None = None,
) -> VideoBlueprint:
    """Map analysis + identity into a contract-valid VideoBlueprint."""
    raw = analyzed.raw
    hook_text = ""
    if analyzed.transcript:
        hook_text = analyzed.transcript[0].text.strip()
    if not hook_text:
        hook_text = (raw.title or f"Quick {identity.niche} win").strip()

    outline: list[str] = []
    if analyzed.overlay_cut_points:
        outline.append("Hook on first beat")
        for i, cp in enumerate(analyzed.overlay_cut_points[:5], start=1):
            outline.append(f"Beat @ {cp.t_seconds:.1f}s — {cp.kind}")
    if len(outline) < 3:
        outline.extend(
            [
                "Deliver core value in the middle third",
                "On-screen text reinforcing key points",
                "Close with CTA + disclosure",
            ]
        )
    outline = outline[:12]

    duration = 15
    if analyzed.transcript:
        duration = int(max(analyzed.transcript, key=lambda s: s.end_seconds).end_seconds + 2)
    duration = max(15, min(90, duration))

    tags = [t.replace(" ", "")[:24] for t in identity.persona.topics[:4]]
    if identity.niche:
        tags.append(identity.niche.replace(" ", "")[:20])

    disclosure = identity.persona.disclosure_line or ""
    caption = f"{disclosure} {raw.title or ''}".strip()

    return VideoBlueprint(
        blueprint_id=blueprint_id or f"vb_{uuid.uuid4().hex[:12]}",
        matrix_id=identity.matrix_id,
        title=(raw.title or f"{identity.display_name} — {identity.niche}").strip()[:200],
        hook=hook_text[:500],
        outline=outline,
        suggested_caption=caption[:2000],
        hashtags=list(dict.fromkeys(tags))[:12],
        audio_id=audio_id,
        duration_seconds_target=duration,
    )
