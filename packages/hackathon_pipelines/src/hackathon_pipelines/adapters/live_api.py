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
    InstagramPostDraft,
    ProductCandidate,
    ReelSurfaceMetrics,
    TemplateDisposition,
    VeoGenerationConfig,
    VideoStructureRecord,
    VideoTemplateRecord,
)
from hackathon_pipelines.ports import GeminiVideoAgentPort, VeoGeneratorPort, VideoUnderstandingPort
from hackathon_pipelines.prototype_bridge import (
    build_fallback_veo_user_prompt,
    build_single_concept_veo_user_prompt_request,
    build_veo_prompt_package,
    write_veo_prompt_package_files,
)
from hackathon_pipelines.video_io import (
    build_output_video_path,
    download_video_to_path,
    render_demo_bundle_video,
)

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

GEMINI_INSTAGRAM_POST_PROMPT = """Create an Instagram-ready caption package for a short UGC product reel.
Respond with ONLY valid JSON:
{
  "caption": "full caption text ready to paste into Instagram, including any hashtags you want in the final post",
  "hashtags": ["#one", "#two"],
  "content_tier": "TOF|MOF|BOF or empty string",
  "funnel_position": "TOF|MOF|BOF or empty string",
  "product_name": "product name",
  "product_tags": ["@brandhandle"],
  "brand_tags": ["@brandhandle"],
  "audio_hook_text": "short hook text",
  "target_niche": "short niche label",
  "thumbnail_text": "optional short cover text",
  "source_blueprint_id": "template or blueprint reference"
}
Keep the caption concise, creator-style, and product-specific.
Do not invent claims that are not supported by the inputs.
"""

PROMPT_ARTIFACTS_ROOT = Path("output") / "hackathon_prompt_artifacts"


def _uses_vertex_ai() -> bool:
    return str(os.getenv("GOOGLE_GENAI_USE_VERTEXAI") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _default_veo_model_id() -> str:
    if _uses_vertex_ai():
        return "veo-3.1-fast-generate-001"
    return "veo-3.1-fast-generate-preview"


def _make_google_genai_client(*, api_key: str | None) -> genai.Client:
    if _uses_vertex_ai():
        return genai.Client()
    if not api_key:
        msg = "GOOGLE_API_KEY (or GEMINI_API_KEY) is not set"
        raise RuntimeError(msg)
    return genai.Client(api_key=api_key)


def _extract_json_object(text: str) -> dict:
    parsed = _extract_json_payload(text)
    if isinstance(parsed, dict):
        return parsed
    msg = "No JSON object found in model output"
    raise ValueError(msg)


def _extract_json_payload(text: str) -> dict | list | None:
    decoder = json.JSONDecoder()
    stripped = text.strip()
    unescaped = text.replace('\\"', '"').replace("\\n", "\n").strip()
    for candidate in (stripped, text, unescaped):
        if not candidate:
            continue
        try:
            parsed, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            return parsed

    for candidate in (stripped, text, unescaped):
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, (dict, list)):
                return parsed

    m = re.search(r"\{[\s\S]*\}", stripped or text)
    if m:
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return None


def _response_text(resp: object) -> str:
    text = getattr(resp, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(resp, "candidates", None) or []
    parts_text: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                parts_text.append(part_text)
    return "\n".join(parts_text).strip()


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _product_description(product: ProductCandidate) -> str:
    notes = (product.notes or "").strip()
    if notes:
        return notes
    return (
        f"{product.title} for a short-form storefront reel. "
        "Show the product clearly, explain what makes it appealing, and keep the pacing UGC-friendly."
    )


def _creative_brief(template: VideoTemplateRecord, product: ProductCandidate) -> str:
    parts = [
        f"Base prompt from winning reel research: {template.veo_prompt_draft}".strip(),
        f"Product to feature: {product.title}.",
        f"Product description: {_product_description(product)}",
    ]
    if template.performance_label is not None:
        parts.append(f"Previous reel feedback label: {template.performance_label.value}.")
    if template.disposition_reason:
        parts.append(f"Template rationale from reel discovery: {template.disposition_reason}.")
    return " ".join(part for part in parts if part)


def _persist_bundle_artifacts(bundle: GenerationBundle) -> GenerationBundle:
    artifact_dir = (
        Path(bundle.prompt_package.artifact_dir)
        if bundle.prompt_package.artifact_dir
        else PROMPT_ARTIFACTS_ROOT / bundle.bundle_id
    )
    prompt_package = bundle.prompt_package
    if not prompt_package.full_prompt:
        prompt_package = build_veo_prompt_package(bundle.veo_prompt or bundle.creative_brief)
    prompt_package = write_veo_prompt_package_files(output_dir=artifact_dir, prompt_package=prompt_package)
    updated_bundle = bundle.model_copy(
        update={
            "prompt_package": prompt_package,
            "veo_prompt": prompt_package.full_prompt,
        }
    )
    bundle_json_path = artifact_dir / "bundle.json"
    bundle_json_path.write_text(json.dumps(updated_bundle.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return updated_bundle


def _default_post_draft(
    template: VideoTemplateRecord,
    product: ProductCandidate,
    *,
    bundle: GenerationBundle,
    structure: VideoStructureRecord | None = None,
    metrics: ReelSurfaceMetrics | None = None,
) -> InstagramPostDraft:
    hook = ""
    if structure is not None and structure.hook_pattern:
        hook = structure.hook_pattern
    elif metrics is not None and metrics.caption_text:
        hook = metrics.caption_text.split("\n", 1)[0].strip()
    if not hook:
        hook = f"{product.title} in a quick creator demo"

    title_words = [word for word in re.split(r"[^A-Za-z0-9]+", product.title.lower()) if word]
    hashtag_words = title_words[:2] or ["ugc", "productdemo"]
    hashtags = [f"#{word}" for word in hashtag_words]
    hashtags.extend(["#ugc", "#creatorfinds", "#instagramreels"])
    deduped_hashtags: list[str] = []
    for tag in hashtags:
        if tag not in deduped_hashtags:
            deduped_hashtags.append(tag)

    caption = (
        f"{hook}\n\n"
        f"{product.title} is the focus in this creator-style reel, "
        "with quick product-forward pacing and a clean payoff.\n\n"
        f"{' '.join(deduped_hashtags[:5])}"
    )
    return InstagramPostDraft(
        caption=caption.strip(),
        hashtags=deduped_hashtags[:5],
        content_tier="MOF",
        funnel_position="MOF",
        product_name=product.title,
        product_tags=[],
        brand_tags=[],
        audio_hook_text=hook[:120],
        target_niche="ugc storefront",
        thumbnail_text="",
        source_blueprint_id=template.template_id,
    )


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
        return _make_google_genai_client(api_key=self._api_key)

    async def _build_single_concept_veo_user_prompt(
        self,
        template: VideoTemplateRecord,
        product: ProductCandidate,
        *,
        product_description: str,
        creative_brief: str,
    ) -> tuple[str, str | None, str]:
        fallback_prompt = build_fallback_veo_user_prompt(
            template,
            product,
            product_description=product_description,
            creative_brief=creative_brief,
        )
        if self._dry_run or not self._api_key:
            return fallback_prompt, "dry_run_fallback_prompt", "fallback"

        client = self._client()
        request = build_single_concept_veo_user_prompt_request(
            template,
            product,
            product_description=product_description,
            creative_brief=creative_brief,
        )
        resp = await client.aio.models.generate_content(
            model=self._model,
            contents=request,
            config=genai_types.GenerateContentConfig(responseMimeType="application/json"),
        )
        text = _response_text(resp)
        try:
            data = _extract_json_object(text)
        except (json.JSONDecodeError, ValueError):
            return fallback_prompt, "invalid_json_fallback_prompt", "fallback"
        user_prompt = str(data.get("user_prompt", "")).strip()
        if not user_prompt:
            return fallback_prompt, "empty_user_prompt_fallback", "fallback"
        return user_prompt, str(data.get("notes", "")).strip() or None, "gemini_single_concept"

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
        resp = await client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(responseMimeType="application/json"),
        )
        text = _response_text(resp)
        try:
            data = _extract_json_object(text)
        except (json.JSONDecodeError, ValueError):
            hook = structure.hook_pattern or "unknown"
            scenes = structure.major_scenes[:3]
            draft = f"UGC vertical video inspired by hook: {hook}; scenes: {scenes}"
            return (TemplateDisposition.ITERATE, "invalid_json_fallback", draft)
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
        bundle_id = f"gen_{uuid.uuid4().hex[:12]}"
        product_description = _product_description(product)
        creative_brief = _creative_brief(template, product)
        user_prompt, prompt_notes, prompt_builder = await self._build_single_concept_veo_user_prompt(
            template,
            product,
            product_description=product_description,
            creative_brief=creative_brief,
        )
        prompt_package = build_veo_prompt_package(user_prompt)
        bundle = GenerationBundle(
            bundle_id=bundle_id,
            template_id=template.template_id,
            product_id=product.product_id,
            veo_prompt=prompt_package.full_prompt,
            product_title=product.title,
            product_description=product_description,
            creative_brief=creative_brief,
            prompt_package=prompt_package,
            generation_config=VeoGenerationConfig(),
            product_image_path=product_image_path,
            avatar_image_path=avatar_image_path,
            reference_image_paths=[product_image_path, avatar_image_path],
            prior_template_metadata={
                "gemini_notes": prompt_notes,
                "prompt_builder": prompt_builder,
                "performance_label": template.performance_label.value if template.performance_label else None,
                "disposition": template.disposition.value,
            },
        )
        return _persist_bundle_artifacts(bundle)

    async def build_instagram_post_draft(
        self,
        template: VideoTemplateRecord,
        product: ProductCandidate,
        *,
        bundle: GenerationBundle,
        artifact: GeneratedVideoArtifact,
        structure: VideoStructureRecord | None = None,
        metrics: ReelSurfaceMetrics | None = None,
    ) -> InstagramPostDraft:
        if self._dry_run or not self._api_key:
            return _default_post_draft(template, product, bundle=bundle, structure=structure, metrics=metrics)

        client = self._client()
        prompt = (
            GEMINI_INSTAGRAM_POST_PROMPT
            + "\n\nINPUT:\n"
            + json.dumps(
                {
                    "template": template.model_dump(mode="json"),
                    "product": product.model_dump(mode="json"),
                    "bundle": bundle.model_dump(mode="json"),
                    "artifact": artifact.model_dump(mode="json"),
                    "structure": structure.model_dump(mode="json") if structure is not None else None,
                    "metrics": metrics.model_dump(mode="json") if metrics is not None else None,
                },
                indent=2,
            )
        )
        resp = await client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(responseMimeType="application/json"),
        )
        text = _response_text(resp)
        try:
            data = _extract_json_object(text)
            return InstagramPostDraft(
                caption=str(data.get("caption", "")).strip()
                or _default_post_draft(template, product, bundle=bundle, structure=structure, metrics=metrics).caption,
                hashtags=_string_list(data.get("hashtags")),
                content_tier=str(data.get("content_tier", "")),
                funnel_position=str(data.get("funnel_position", "")),
                product_name=str(data.get("product_name", product.title)),
                product_tags=_string_list(data.get("product_tags")),
                brand_tags=_string_list(data.get("brand_tags")),
                audio_hook_text=str(data.get("audio_hook_text", "")),
                target_niche=str(data.get("target_niche", "")),
                thumbnail_text=str(data.get("thumbnail_text", "")),
                source_blueprint_id=str(data.get("source_blueprint_id", template.template_id)),
            )
        except Exception:
            return _default_post_draft(template, product, bundle=bundle, structure=structure, metrics=metrics)


class VeoVideoGenerator(VeoGeneratorPort):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dry_run: bool = True,
        output_dir: str | Path = Path("output") / "hackathon_videos",
    ) -> None:
        self._dry_run = dry_run
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self._model = model or os.getenv("VEO_MODEL_ID", _default_veo_model_id())
        self._output_dir = Path(output_dir)

    async def generate_ugc_video(self, bundle: GenerationBundle) -> GeneratedVideoArtifact:
        artifact_id = f"vid_{uuid.uuid4().hex[:12]}"
        output_path = build_output_video_path(artifact_id=artifact_id, output_dir=self._output_dir)
        generation_config = bundle.generation_config
        if self._dry_run or not self._api_key:
            render_demo_bundle_video(bundle=bundle, output_path=output_path)
            return GeneratedVideoArtifact(
                artifact_id=artifact_id,
                bundle_id=bundle.bundle_id,
                video_uri=None,
                video_path=str(output_path),
                model_id=self._model,
                reference_image_paths=list(bundle.reference_image_paths),
                provider_metadata={
                    "mode": "dry_run",
                    "local_demo_video": str(output_path),
                    "generation_config": generation_config.model_dump(mode="json"),
                },
            )

        import asyncio

        client = _make_google_genai_client(api_key=self._api_key)
        ordered_reference_paths: list[str] = []
        for candidate in [
            bundle.product_image_path,
            bundle.avatar_image_path,
            *bundle.reference_image_paths,
        ]:
            if candidate and candidate not in ordered_reference_paths:
                ordered_reference_paths.append(candidate)
        reference_image_paths = ordered_reference_paths[:3]
        reference_images = [
            genai_types.VideoGenerationReferenceImage(
                image=genai_types.Image.from_file(location=path),
                reference_type="asset",
            )
            for path in reference_image_paths
        ]
        operation = await client.aio.models.generate_videos(
            model=self._model,
            prompt=bundle.veo_prompt,
            config=genai_types.GenerateVideosConfig(
                reference_images=reference_images,
                number_of_videos=1,
                duration_seconds=generation_config.duration_seconds,
                aspect_ratio=generation_config.aspect_ratio,
            ),
        )
        while not operation.done:
            await asyncio.sleep(5)
            operation = await client.aio.operations.get(operation)
        result = operation.result
        if not result or not result.generated_videos:
            msg = "Veo generation returned no videos"
            raise RuntimeError(msg)
        video = result.generated_videos[0].video
        uri = getattr(video, "uri", None) if video else None
        local_video_path: str | None = None
        if video is not None:
            try:
                await asyncio.to_thread(client.files.download, file=video)
                await asyncio.to_thread(video.save, str(output_path))
                local_video_path = str(output_path)
            except Exception as exc:
                if uri:
                    try:
                        downloaded = await download_video_to_path(uri, output_path)
                        local_video_path = str(downloaded)
                    except Exception as fallback_exc:
                        local_video_path = None
                        download_error = f"sdk_download={exc}; url_download={fallback_exc}"
                    else:
                        download_error = None
                else:
                    local_video_path = None
                    download_error = str(exc)
            else:
                download_error = None
        else:
            download_error = None
        return GeneratedVideoArtifact(
            artifact_id=artifact_id,
            bundle_id=bundle.bundle_id,
            video_uri=uri,
            video_path=local_video_path,
            model_id=self._model,
            reference_image_paths=reference_image_paths,
            provider_metadata={
                "reference_image_paths": reference_image_paths,
                "live_reference_mode": "separate_asset_references",
                "local_output_path": str(output_path),
                "download_error": download_error,
                "generation_config": generation_config.model_dump(mode="json"),
            },
        )
