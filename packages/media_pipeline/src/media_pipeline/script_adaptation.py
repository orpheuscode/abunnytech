from __future__ import annotations

from media_pipeline.models import AdaptedScript, ScriptSegment
from pipeline_contracts.models import VideoBlueprint


def adapt_script_from_blueprint(blueprint: VideoBlueprint) -> AdaptedScript:
    """
    Expand blueprint hook, outline beats, and implied CTA into timed segments.

    Durations split the blueprint duration across hook, beats, and a short CTA tail
    so total segment time matches ``duration_seconds_target``.
    """
    total = float(blueprint.duration_seconds_target)
    outline = blueprint.outline or []
    n_beats = max(len(outline), 1)

    # Reserve ~18% hook, ~12% CTA, remainder across beats
    hook_dur = min(3.0, total * 0.18)
    cta_dur = min(2.5, total * 0.12)
    middle = max(total - hook_dur - cta_dur, 0.0)
    per_beat = middle / n_beats

    segments: list[ScriptSegment] = [
        ScriptSegment(role="hook", text=blueprint.hook.strip(), duration_seconds=hook_dur),
    ]
    if outline:
        for i, beat in enumerate(outline):
            segments.append(
                ScriptSegment(
                    role="beat",
                    text=str(beat).strip(),
                    duration_seconds=per_beat,
                    beat_index=i,
                )
            )
    else:
        segments.append(
            ScriptSegment(
                role="beat",
                text=blueprint.title.strip(),
                duration_seconds=middle,
                beat_index=0,
            )
        )
    segments.append(
        ScriptSegment(
            role="cta",
            text="Follow for more tips — see caption for details.",
            duration_seconds=cta_dur,
        )
    )

    # Normalize to exact total (floating drift)
    drift = total - sum(s.duration_seconds for s in segments)
    if segments and abs(drift) > 1e-6:
        segments[-1] = segments[-1].model_copy(
            update={"duration_seconds": max(0.0, segments[-1].duration_seconds + drift)}
        )

    voice_parts: list[str] = []
    for s in segments:
        if s.role == "hook":
            voice_parts.append(s.text)
        elif s.role == "beat":
            voice_parts.append(s.text)
        else:
            voice_parts.append(s.text)
    full_voice = " ".join(voice_parts)

    return AdaptedScript(
        blueprint_id=blueprint.blueprint_id,
        total_duration_seconds=total,
        segments=segments,
        full_voiceover_text=full_voice,
    )
