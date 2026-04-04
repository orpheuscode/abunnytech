from __future__ import annotations

import uuid

from pydantic import HttpUrl

from abunny_stage0_identity.models_input import PersonaSetup
from pipeline_contracts.models.identity import VoicePackRef


def provision_voice(
    setup: PersonaSetup,
    *,
    matrix_id: str,
    dry_run: bool,
) -> VoicePackRef:
    """
    ElevenLabs voice provisioning (stub).

    Live mode would use ELEVENLABS_API_KEY; dry-run returns mock voice ids.
    """
    hint = setup.integrations.elevenlabs_voice_id
    if dry_run:
        suffix = uuid.uuid4().hex[:10]
        voice_id = hint or f"el_dry_{matrix_id}_{suffix}"
        return VoicePackRef(
            voice_id=voice_id,
            provider="elevenlabs",
            sample_url=HttpUrl("https://example.com/fixtures/voice-sample-placeholder.mp3"),
        )
    if hint:
        return VoicePackRef(voice_id=hint, provider="elevenlabs")
    msg = "ElevenLabs voice id missing — set integrations.elevenlabs_voice_id or use dry-run"
    raise ValueError(msg)
