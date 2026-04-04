from __future__ import annotations

import json

from abunny_stage0_identity.compiler import IdentityMatrixCompiler
from abunny_stage0_identity.models_input import PersonaSetup
from pipeline_contracts.models.identity import IdentityMatrix


def build_system_prompt(setup: PersonaSetup, identity: IdentityMatrix, *, dry_run: bool) -> str:
    """
    Single markdown document for downstream LLM calls (stages 1–5).

    Keeps contract fields in `IdentityMatrix` lean; narrative and operational
    detail live here for prompt injection.
    """
    c = IdentityMatrixCompiler(setup, dry_run=dry_run)
    demo = c.normalize_demographics()
    cadence_n, windows = c.normalize_posting_cadence()
    comment = c.normalize_comment_style()
    dm_rules = c.normalize_dm_rules()
    visual = c.normalize_visual_style()
    personality = setup.personality

    matrix_json = json.dumps(identity.model_dump(mode="json"), indent=2)

    lines = [
        "# Creator identity — system prompt",
        "",
        "Use this document as the authoritative persona brief. Prefer facts here over improvisation.",
        "",
        "## Identity matrix (contract snapshot)",
        "",
        "```json",
        matrix_json,
        "```",
        "",
        "## Role",
        "",
        f"You embody **{identity.display_name}**, focused on **{identity.niche}**.",
        "",
        "## Audience & demographics",
        "",
        f"- Locale: {demo.get('locale') or 'unspecified'}",
        f"- Age range: {demo.get('age_range') or 'unspecified'}",
        f"- Gender presentation: {demo.get('gender_presentation') or 'unspecified'}",
        f"- Location hint: {demo.get('location_hint') or 'unspecified'}",
        "",
        "## Personality & voice",
        "",
        f"- Traits: {', '.join(personality.traits) or '—'}",
        f"- Energy: {personality.energy}",
        f"- Spoken voice (description): {personality.voice_description or '—'}",
        f"- Persona tone (contract): {identity.persona.tone}",
        "",
        "## Product categories",
        "",
        "\n".join(f"- {x}" for x in c.normalize_product_categories()) or "- (none specified)",
        "",
        "## Posting cadence",
        "",
        f"- Target posts per week: {cadence_n}",
        f"- Preferred windows (as authored): {', '.join(windows) if windows else '—'}",
        "",
        "## Comment style",
        "",
        f"- Length: {comment['length']}",
        f"- Emoji use: {comment['emoji_use']}",
        f"- Signature phrases: {', '.join(comment['signature_phrases']) or '—'}",
        "",
        "## DM trigger rules",
        "",
    ]
    if dm_rules:
        for r in dm_rules:
            note = f" ({r['notes']})" if r.get("notes") else ""
            lines.append(f"- When **{r['match']}** → **{r['action']}**{note}")
    else:
        lines.append("- (no rules — use platform defaults and brand safety)")
    lines.extend(
        [
            "",
            "## Visual style",
            "",
            f"- Palette: {', '.join(visual['palette']) or '—'}",
            f"- Lighting: {visual.get('lighting') or '—'}",
            f"- Camera: {visual.get('camera') or '—'}",
            f"- Wardrobe: {visual.get('wardrobe_notes') or '—'}",
            f"- Background / set: {visual.get('background_notes') or '—'}",
            "",
        "## Platform targets",
        "",
        "\n".join(f"- {p.value}" for p in identity.platform_targets) or "- (none)",
            "",
            "## Disclosure",
            "",
            identity.persona.disclosure_line
            or "Disclose synthetic / assistant origin when platform policy requires.",
            "",
            "## Integrations (reference ids)",
            "",
            f"- dry_run: {dry_run}",
            f"- avatar: provider={identity.avatar.provider} id={identity.avatar.avatar_id}",
            f"- voice: provider={identity.voice.provider} id={identity.voice.voice_id}",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
