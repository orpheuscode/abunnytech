from __future__ import annotations

import uuid

from pydantic import HttpUrl

from abunny_stage0_identity.models_input import PersonaSetup
from pipeline_contracts.models.identity import AvatarPackRef


def resolve_avatar(
    setup: PersonaSetup,
    *,
    matrix_id: str,
    dry_run: bool,
) -> AvatarPackRef:
    """
    Higgsfield character generation / import (stub).

    Live mode would call Higgsfield APIs using HIGGSFIELD_API_KEY; dry-run returns
    deterministic fixture refs without network access.
    """
    hint = setup.integrations.higgsfield_character_id
    if dry_run:
        suffix = uuid.uuid4().hex[:10]
        avatar_id = hint or f"hf_dry_{matrix_id}_{suffix}"
        return AvatarPackRef(
            avatar_id=avatar_id,
            provider="higgsfield",
            preview_url=HttpUrl("https://example.com/fixtures/higgsfield-preview.png"),
        )
    if hint:
        return AvatarPackRef(avatar_id=hint, provider="higgsfield")
    msg = "Higgsfield character id missing — set integrations.higgsfield_character_id or use dry-run"
    raise ValueError(msg)
