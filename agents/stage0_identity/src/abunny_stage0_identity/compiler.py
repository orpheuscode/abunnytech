from __future__ import annotations

from abunny_stage0_identity.adapters.elevenlabs import provision_voice
from abunny_stage0_identity.adapters.higgsfield import resolve_avatar
from abunny_stage0_identity.models_input import PersonaSetup
from pipeline_contracts.models.enums import PlatformTarget
from pipeline_contracts.models.identity import IdentityMatrix, PersonaAxis


def parse_platform_targets(raw: list[str]) -> list[PlatformTarget]:
    if not raw:
        return [PlatformTarget.TIKTOK, PlatformTarget.SHORTS]
    out: list[PlatformTarget] = []
    for p in raw:
        key = p.strip().lower()
        try:
            out.append(PlatformTarget(key))
        except ValueError as e:
            allowed = ", ".join(sorted(x.value for x in PlatformTarget))
            msg = f"Unknown platform target {p!r}; expected one of: {allowed}"
            raise ValueError(msg) from e
    return out


def _norm_str(s: str) -> str:
    return " ".join(s.split())


def _norm_niche(niche: str) -> str:
    return _norm_str(niche.strip())


class IdentityMatrixCompiler:
    """Maps rich PersonaSetup into contract `IdentityMatrix` + `PersonaAxis` fields."""

    def __init__(self, setup: PersonaSetup, *, dry_run: bool) -> None:
        self.setup = setup
        self.dry_run = dry_run

    def normalize_demographics(self) -> dict[str, str | None]:
        d = self.setup.demographics
        return {
            "age_range": d.age_range.strip() if d.age_range else None,
            "locale": d.locale.strip() or "en-US",
            "gender_presentation": d.gender_presentation.strip() if d.gender_presentation else None,
            "location_hint": d.location_hint.strip() if d.location_hint else None,
        }

    def normalize_personality_tone(self) -> str:
        p = self.setup.personality
        traits = ", ".join(t.strip() for t in p.traits if t.strip())
        base = f"{p.energy.strip()} energy"
        if traits:
            return _norm_str(f"{base}; {traits}")
        return _norm_str(base)

    def normalize_niche(self) -> str:
        return _norm_niche(self.setup.niche)

    def normalize_product_categories(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for c in self.setup.product_categories:
            key = c.casefold()
            if key not in seen:
                seen.add(key)
                out.append(c)
        return out

    def normalize_posting_cadence(self) -> tuple[int, list[str]]:
        c = self.setup.posting_cadence
        windows = [_norm_str(w) for w in c.best_windows_utc if w.strip()]
        return c.posts_per_week, windows

    def normalize_comment_style(self) -> dict[str, str | list[str]]:
        cs = self.setup.comment_style
        return {
            "length": cs.length.strip(),
            "emoji_use": cs.emoji_use.strip(),
            "signature_phrases": [s.strip() for s in cs.signature_phrases if s.strip()],
        }

    def normalize_dm_rules(self) -> list[dict[str, str | None]]:
        return [
            {"match": r.match.strip(), "action": r.action.strip(), "notes": r.notes}
            for r in self.setup.dm_trigger_rules
            if r.match.strip() and r.action.strip()
        ]

    def normalize_visual_style(self) -> dict[str, str | list[str] | None]:
        v = self.setup.visual_style
        palette = [p.strip() for p in v.palette if p.strip()]
        return {
            "palette": palette,
            "lighting": v.lighting.strip() if v.lighting else None,
            "camera": v.camera.strip() if v.camera else None,
            "wardrobe_notes": v.wardrobe_notes.strip() if v.wardrobe_notes else None,
            "background_notes": v.background_notes.strip() if v.background_notes else None,
        }

    def persona_topics(self) -> list[str]:
        """Contract `PersonaAxis.topics`: concise machine-facing tags for downstream stages."""
        topics: list[str] = []
        topics.append(f"niche:{self.normalize_niche()}")
        for cat in self.normalize_product_categories():
            topics.append(f"category:{cat}")
        demo = self.normalize_demographics()
        if demo["age_range"]:
            topics.append(f"audience_age:{demo['age_range']}")
        if demo["locale"]:
            topics.append(f"locale:{demo['locale']}")
        posts, _windows = self.normalize_posting_cadence()
        topics.append(f"cadence_posts_per_week:{posts}")
        return topics

    def compile_persona_axis(self) -> PersonaAxis:
        disclosure = self.setup.disclosure_line
        if disclosure:
            disclosure = disclosure.strip()
        return PersonaAxis(
            tone=self.normalize_personality_tone(),
            topics=self.persona_topics(),
            avoid_topics=list(self.setup.avoid_topics),
            disclosure_line=disclosure or None,
        )

    def compile_identity_matrix(self, matrix_id: str) -> IdentityMatrix:
        persona = self.compile_persona_axis()
        avatar = resolve_avatar(self.setup, matrix_id=matrix_id, dry_run=self.dry_run)
        voice = provision_voice(self.setup, matrix_id=matrix_id, dry_run=self.dry_run)
        platforms = parse_platform_targets(self.setup.platform_targets)
        return IdentityMatrix(
            matrix_id=matrix_id,
            display_name=_norm_str(self.setup.display_name),
            niche=self.normalize_niche(),
            persona=persona,
            avatar=avatar,
            voice=voice,
            platform_targets=platforms,
        )


def compile_identity_matrix(setup: PersonaSetup, matrix_id: str, *, dry_run: bool) -> IdentityMatrix:
    return IdentityMatrixCompiler(setup, dry_run=dry_run).compile_identity_matrix(matrix_id)
