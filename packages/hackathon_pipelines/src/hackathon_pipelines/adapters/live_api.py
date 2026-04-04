"""Live TwelveLabs, Gemini orchestration, and Veo — with explicit dry-run shims for CI."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import uuid
from pathlib import Path

from google import genai
from google.genai import types as genai_types

from hackathon_pipelines.contracts import (
    GeneratedVideoArtifact,
    GenerationBundle,
    ProductCandidate,
    TemplateDisposition,
    VideoStructureRecord,
    VideoTemplateRecord,
)
from hackathon_pipelines.ports import GeminiVideoAgentPort, VeoGeneratorPort, VideoUnderstandingPort

TWELVE_LABS_STRUCTURE_PROMPT = """\
You are a video analyst. Watch the video and respond with ONLY valid JSON (no markdown), keys:
{
  "major_scenes": ["string", ...],
  "hook_pattern": "string describing opening hook",
  "audio_music_cues": "string",
  "visual_style": "string",
  "sequence_description": "string narrative of shot order",
  "on_screen_text_notes": "string or empty"
}
"""

GEMINI_DECISION_PROMPT = """You coordinate UGC video templates. Given a JSON structure from video analysis and a list of
existing templates (id, disposition, performance_label), respond with ONLY valid JSON:
{"decision":"remake"|"iterate"|"discard","reason":"short string","veo_prompt_draft":"detailed Veo-oriented prompt"}
Rules: discard weak duplicates; iterate when a small change could beat prior; remake when structure is novel and strong.
"""


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        msg = "No JSON object found in model output"
        raise ValueError(msg)
    return json.loads(m.group(0))


class TwelveLabsUnderstanding(VideoUnderstandingPort):
    def __init__(self, *, api_key: str | None = None, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._api_key = api_key or os.getenv("TWELVE_LABS_API_KEY") or os.getenv("TWELVELABS_API_KEY")

    async def analyze_reel_file(self, local_video_path: str, *, reel_id: str) -> VideoStructureRecord:
        record_id = f"struct_{uuid.uuid4().hex[:12]}"
        if self._dry_run or not self._api_key:
            return VideoStructureRecord(
                record_id=record_id,
                source_reel_id=reel_id,
                major_scenes=["dry_run_scene"],
                hook_pattern="dry_run_hook",
                audio_music_cues="dry_run_audio",
                visual_style="dry_run_style",
                sequence_description="dry_run_sequence",
                on_screen_text_notes="",
                raw_analysis_text="{}",
            )

        from twelvelabs import TwelveLabs
        from twelvelabs.types.video_context import VideoContext_Base64String

        path = Path(local_video_path)
        raw = path.read_bytes()
        b64 = base64.standard_b64encode(raw).decode("ascii")

        def _call_tl() -> object:
            client = TwelveLabs(api_key=self._api_key)
            return client.analyze(
                prompt=TWELVE_LABS_STRUCTURE_PROMPT,
                video=VideoContext_Base64String(base_64_string=b64),
                temperature=0.2,
            )

        resp = await asyncio.to_thread(_call_tl)
        raw_text = resp.data if isinstance(resp.data, str) else str(resp.data)
        try:
            data = _extract_json_object(raw_text)
        except (json.JSONDecodeError, ValueError):
            data = {
                "major_scenes": [],
                "hook_pattern": None,
                "audio_music_cues": None,
                "visual_style": raw_text[:2000],
                "sequence_description": None,
                "on_screen_text_notes": None,
            }
        return VideoStructureRecord(
            record_id=record_id,
            source_reel_id=reel_id,
            major_scenes=list(data.get("major_scenes") or []),
            hook_pattern=data.get("hook_pattern"),
            audio_music_cues=data.get("audio_music_cues"),
            visual_style=data.get("visual_style"),
            sequence_description=data.get("sequence_description"),
            on_screen_text_notes=data.get("on_screen_text_notes"),
            raw_analysis_text=raw_text,
        )


class GeminiTemplateAgent(GeminiVideoAgentPort):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dry_run: bool = True,
    ) -> None:
        self._dry_run = dry_run
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self._model = model or os.getenv("GEMINI_ORCHESTRATION_MODEL", "gemini-2.5-flash")

    def _client(self) -> genai.Client:
        if not self._api_key:
            msg = "GOOGLE_API_KEY (or GEMINI_API_KEY) is not set"
            raise RuntimeError(msg)
        return genai.Client(api_key=self._api_key)

    async def decide_template_disposition(
        self,
        structure: VideoStructureRecord,
        *,
        peer_templates: list[VideoTemplateRecord],
    ) -> tuple[TemplateDisposition, str, str]:
        if self._dry_run or not self._api_key:
            hook = structure.hook_pattern or "unknown"
            scenes = structure.major_scenes[:3]
            draft = f"UGC vertical video inspired by hook: {hook}; scenes: {scenes}"
            return (TemplateDisposition.ITERATE, "dry_run_default", draft)

        payload = {
            "new_structure": structure.model_dump(mode="json"),
            "existing_templates": [t.model_dump(mode="json") for t in peer_templates],
        }
        client = self._client()
        prompt = GEMINI_DECISION_PROMPT + "\n\nINPUT:\n" + json.dumps(payload, indent=2)
        resp = await client.aio.models.generate_content(model=self._model, contents=prompt)
        text = getattr(resp, "text", None) or ""
        data = _extract_json_object(text)
        raw_decision = str(data.get("decision", "iterate")).lower()
        try:
            decision = TemplateDisposition(raw_decision)
        except ValueError:
            decision = TemplateDisposition.ITERATE
        return decision, str(data.get("reason", "")), str(data.get("veo_prompt_draft", ""))

    async def build_generation_bundle(
        self,
        template: VideoTemplateRecord,
        product: ProductCandidate,
        *,
        product_image_path: str,
        avatar_image_path: str,
    ) -> GenerationBundle:
        if self._dry_run or not self._api_key:
            return GenerationBundle(
                bundle_id=f"gen_{uuid.uuid4().hex[:12]}",
                template_id=template.template_id,
                product_id=product.product_id,
                veo_prompt=template.veo_prompt_draft,
                product_image_path=product_image_path,
                avatar_image_path=avatar_image_path,
                prior_template_metadata={"disposition": template.disposition.value},
            )

        client = self._client()
        prompt = (
            "Build one consolidated Veo prompt for a short UGC product video. "
            "Return ONLY valid JSON: {\"veo_prompt\":\"...\",\"notes\":\"...\"}\n\n"
            + json.dumps(
                {
                    "template": template.model_dump(mode="json"),
                    "product": product.model_dump(mode="json"),
                    "product_image_path": product_image_path,
                    "avatar_image_path": avatar_image_path,
                },
                indent=2,
            )
        )
        resp = await client.aio.models.generate_content(model=self._model, contents=prompt)
        text = getattr(resp, "text", None) or ""
        data = _extract_json_object(text)
        veo_prompt = str(data.get("veo_prompt", template.veo_prompt_draft))
        return GenerationBundle(
            bundle_id=f"gen_{uuid.uuid4().hex[:12]}",
            template_id=template.template_id,
            product_id=product.product_id,
            veo_prompt=veo_prompt,
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
            prior_template_metadata={"gemini_notes": data.get("notes")},
        )


class VeoVideoGenerator(VeoGeneratorPort):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dry_run: bool = True,
    ) -> None:
        self._dry_run = dry_run
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self._model = model or os.getenv("VEO_MODEL_ID", "veo-3.1-generate-preview")

    async def generate_ugc_video(self, bundle: GenerationBundle) -> GeneratedVideoArtifact:
        artifact_id = f"vid_{uuid.uuid4().hex[:12]}"
        if self._dry_run or not self._api_key:
            return GeneratedVideoArtifact(
                artifact_id=artifact_id,
                bundle_id=bundle.bundle_id,
                video_uri=None,
                video_path=None,
                model_id=self._model,
            )

        import asyncio

        client = genai.Client(api_key=self._api_key)
        img = genai_types.Image.from_file(location=bundle.product_image_path)
        source = genai_types.GenerateVideosSource(prompt=bundle.veo_prompt, image=img)
        operation = await client.aio.models.generate_videos(model=self._model, source=source)
        while not operation.done:
            await asyncio.sleep(5)
            operation = await client.aio.operations.get(operation)
        result = operation.result
        if not result or not result.generated_videos:
            msg = "Veo generation returned no videos"
            raise RuntimeError(msg)
        video = result.generated_videos[0].video
        uri = getattr(video, "uri", None) if video else None
        return GeneratedVideoArtifact(
            artifact_id=artifact_id,
            bundle_id=bundle.bundle_id,
            video_uri=uri,
            video_path=None,
            model_id=self._model,
        )
