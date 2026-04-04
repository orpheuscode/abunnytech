from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class DemographicsInput(BaseModel):
    model_config = {"extra": "forbid"}

    age_range: str | None = None
    locale: str = "en-US"
    gender_presentation: str | None = None
    location_hint: str | None = None


class PersonalityInput(BaseModel):
    model_config = {"extra": "forbid"}

    traits: list[str] = Field(default_factory=list)
    energy: str = "medium"
    voice_description: str | None = None


class PostingCadenceInput(BaseModel):
    model_config = {"extra": "forbid"}

    posts_per_week: int = Field(default=3, ge=0, le=21)
    best_windows_utc: list[str] = Field(
        default_factory=list,
        description="e.g. 18:00-21:00 — stored as strings for portability",
    )


class CommentStyleInput(BaseModel):
    model_config = {"extra": "forbid"}

    length: str = "medium"
    emoji_use: str = "light"
    signature_phrases: list[str] = Field(default_factory=list)


class DMTriggerRuleInput(BaseModel):
    model_config = {"extra": "forbid"}

    match: str = Field(description="keyword, regex id, or intent label")
    action: str = Field(description="e.g. send_link_tree, escalate_human")
    notes: str | None = None


class VisualStyleInput(BaseModel):
    model_config = {"extra": "forbid"}

    palette: list[str] = Field(default_factory=list)
    lighting: str | None = None
    camera: str | None = None
    wardrobe_notes: str | None = None
    background_notes: str | None = None


class IntegrationHintsInput(BaseModel):
    """Optional upstream ids; never required for dry-run compilation."""

    model_config = {"extra": "forbid"}

    higgsfield_character_id: str | None = None
    nano_banana_collection_id: str | None = None
    elevenlabs_voice_id: str | None = None


class PersonaSetup(BaseModel):
    """Authoring-time persona document (YAML/JSON). Not a pipeline contract."""

    model_config = {"extra": "forbid"}

    display_name: str
    niche: str
    demographics: DemographicsInput = Field(default_factory=DemographicsInput)
    personality: PersonalityInput = Field(default_factory=PersonalityInput)
    product_categories: list[str] = Field(default_factory=list)
    posting_cadence: PostingCadenceInput = Field(default_factory=PostingCadenceInput)
    comment_style: CommentStyleInput = Field(default_factory=CommentStyleInput)
    dm_trigger_rules: list[DMTriggerRuleInput] = Field(default_factory=list)
    visual_style: VisualStyleInput = Field(default_factory=VisualStyleInput)
    platform_targets: list[str] = Field(default_factory=lambda: ["tiktok", "shorts"])
    avoid_topics: list[str] = Field(default_factory=list)
    disclosure_line: str | None = Field(
        default=None,
        description="AI / sandbox disclosure shown to viewers",
    )
    integrations: IntegrationHintsInput = Field(default_factory=IntegrationHintsInput)

    @field_validator("display_name", "niche")
    @classmethod
    def strip_nonempty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            msg = "must be non-empty"
            raise ValueError(msg)
        return s

    @field_validator("product_categories", "platform_targets")
    @classmethod
    def strip_list(cls, v: list[str]) -> list[str]:
        return [x.strip() for x in v if x.strip()]
