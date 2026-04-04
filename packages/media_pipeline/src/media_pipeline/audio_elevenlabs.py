from __future__ import annotations

from pathlib import Path
from typing import Protocol

from media_pipeline.models import AdaptedScript, ElevenLabsAudioRequest


def build_elevenlabs_request(
    script: AdaptedScript,
    voice_id: str,
    *,
    model_id: str = "eleven_multilingual_v2",
) -> ElevenLabsAudioRequest:
    """Build a stable ElevenLabs-shaped request from adapted narration."""
    text = script.full_voiceover_text.strip() or script.segments[0].text
    return ElevenLabsAudioRequest(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
    )


class AudioSynthesisAdapter(Protocol):
    """Pluggable TTS: real ElevenLabs client implements this; tests use mocks."""

    def synthesize_to_path(
        self,
        request: ElevenLabsAudioRequest,
        output_path: Path,
        *,
        dry_run: bool,
    ) -> Path: ...


class MockElevenLabsAdapter:
    """Writes a tiny placeholder file and returns path; no network."""

    def synthesize_to_path(
        self,
        request: ElevenLabsAudioRequest,
        output_path: Path,
        *,
        dry_run: bool,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if dry_run:
            output_path.write_text(
                f"DRY_RUN_TTS\nvoice={request.voice_id}\nchars={len(request.text)}\n",
                encoding="utf-8",
            )
            return output_path
        stub = (
            f"MOCK_MP3_PLACEHOLDER\nvoice={request.voice_id}\n"
            f"text_len={len(request.text)}\n"
        ).encode()
        output_path.write_bytes(stub)
        return output_path
