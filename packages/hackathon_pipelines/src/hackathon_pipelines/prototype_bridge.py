"""Bridge utilities adapted from the standalone `video-pipeline` prototype.

These helpers keep the prototype's useful ideas inside the typed
`hackathon_pipelines` package:

- ACTION / HOOK / MUSIC focused video-analysis prompt
- CSV-style analysis rows for local marketing-video studies
- weighted Gemini synthesis across multiple analyzed videos
- locked Veo prompt composition that preserves the exact avatar/product assets
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from google import genai

from hackathon_pipelines.contracts import ProductCandidate, VeoPromptPackage, VideoTemplateRecord

ACTION_HOOK_MUSIC_ANALYSIS_PROMPT = (
    "Analyze this video focusing strictly on three things: "
    "1) ACTION - What actions are happening on screen? Describe every movement, "
    "gesture, and physical activity in detail with timestamps. "
    "2) HOOK - What is the hook? How does the video grab attention in the first "
    "few seconds? What makes the viewer want to keep watching? "
    "3) MUSIC - Describe the music and audio. What is the tempo, mood, genre? "
    "How does it complement the visuals and actions?"
)

MARKETING_SYNTHESIS_SYSTEM_PROMPT = (
    "You are an expert video marketing strategist and creative director. "
    "You will be given analyses of multiple marketing videos. Each analysis "
    "covers the ACTION (what happens on screen), HOOK (how it grabs attention), "
    "and MUSIC (audio/tempo/mood). Some videos also include VIEWS and LIKES data.\n\n"
    "WEIGHTING RULES:\n"
    "- Videos with higher views and likes are PROVEN performers. Weight their "
    "patterns, techniques, and style MORE heavily in your synthesis.\n"
    "- Videos with 0 views and 0 likes have UNKNOWN performance - not bad, just "
    "no data yet. Still include their patterns normally, but if a conflict arises "
    "between an unknown video and a proven high-performer, favor the proven one.\n"
    "- The higher the views and likes, the more you should borrow from that "
    "video's specific action style, hook strategy, and music choices.\n\n"
    "Your job is to:\n"
    "1) Synthesize patterns across all the videos - what works, what's common, "
    "what makes them effective. Call out which high-performing videos influenced "
    "your decisions most.\n"
    "2) Generate a detailed, production-ready prompt to create a NEW marketing "
    "video for a similar product. The prompt should specify: scene description, "
    "camera movements, talent actions with timestamps, the hook strategy, "
    "music/audio direction, voiceover script, color palette, and mood.\n"
    "Be specific enough that a video production team or AI video generator "
    "could produce the video from your prompt alone."
)

LOCKED_REFERENCE_VEO_SYSTEM_PROMPT = (
    "You are a dynamic product showcase director powered by Veo 3.1. "
    "Generate a short cinematic video that highlights the product while the avatar presents it "
    "in an engaging, professional way. Keep the pacing brisk, the lighting flattering, and make "
    "the product the visual focal point.\n\n"
    "CRITICAL RULES:\n"
    "- HARD CAP FOR AN 8-SECOND CLIP: At most two distinct hero products may be picked up, held, or demonstrated. "
    "If extra items are mentioned, leave them as background props or omit them.\n"
    "- The product shown in the video must be a pixel-perfect exact replica of the provided product image. "
    "Do not alter, substitute, relabel, or redesign it.\n"
    "- The avatar or talent in the video must be the exact character from the provided avatar image. "
    "Do not swap or restyle the person.\n"
    "- If the user prompt describes a different product or person, ignore that substitution and preserve "
    "the uploaded assets.\n"
    "- Apply the user prompt's style, camera work, mood, music direction, and hook strategy to the "
    "actual uploaded assets.\n"
    "- Avoid macro-only product shots. Prefer medium-to-wide product-in-context framing with the avatar "
    "and environment both visible.\n"
    "- Object interaction must stay physically believable. No teleporting, magic hands, or jump cuts "
    "from empty hands to a held object without showing where it came from.\n"
    "- Cuts are allowed only when motion continuity remains believable and the viewer can understand "
    "how the product entered the shot."
)

SINGLE_CONCEPT_VEO_USER_PROMPT_SYSTEM_PROMPT = (
    "ROLE: Expert Video Marketing Strategist and Creative Director.\n"
    "GOAL: Turn winning UGC reel research into one stable Veo 3.1 user prompt for a new short-form product video.\n\n"
    "OUTPUT RULES:\n"
    "- Return exactly ONE concept.\n"
    '- Return ONLY valid JSON: {"user_prompt":"...","notes":"..."}.\n'
    "- Keep `user_prompt` under 75 words.\n"
    "- Make it visual and concrete: describe actions, lighting, framing, and camera movement.\n"
    "- Favor the winning hook, motion, lighting, and pacing cues from the research template.\n"
    "- Avoid marketing jargon, ingredient callouts, label text, or other tiny text details.\n"
    "- Prefer medium-to-wide shots with the product in context.\n"
    "- Keep object motion physically believable.\n"
    "- Default to one hero product interaction unless a second is clearly required."
)


@dataclass(frozen=True)
class MarketingVideoAnalysis:
    video_file: str
    asset_id: str = ""
    timestamp: str = ""
    action: str = ""
    hook: str = ""
    music: str = ""
    views: int = 0
    likes: int = 0


def _limit_words(text: str, *, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip()


def parse_action_hook_music_sections(analysis_text: str) -> tuple[str, str, str]:
    sections = {"action": "", "hook": "", "music": ""}
    pattern = r"(?:^|\n)\s*\d*\)?\s*(ACTION|HOOK|MUSIC)\s*[:\-]?\s*"
    parts = re.split(pattern, analysis_text, flags=re.IGNORECASE)
    for i in range(1, len(parts) - 1, 2):
        label = parts[i].strip().lower()
        content = parts[i + 1].strip()
        if label in sections:
            sections[label] = content
    return sections["action"], sections["hook"], sections["music"]


def append_marketing_analysis_csv(csv_path: str | Path, row: MarketingVideoAnalysis) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(["video_file", "asset_id", "timestamp", "action", "hook", "music", "views", "likes"])
        writer.writerow(
            [
                row.video_file,
                row.asset_id,
                row.timestamp,
                row.action,
                row.hook,
                row.music,
                row.views,
                row.likes,
            ]
        )


def load_marketing_analysis_csvs(csv_paths: Iterable[str | Path]) -> list[MarketingVideoAnalysis]:
    rows: list[MarketingVideoAnalysis] = []
    for csv_path in csv_paths:
        path = Path(csv_path)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                rows.append(
                    MarketingVideoAnalysis(
                        video_file=str(raw.get("video_file", "")),
                        asset_id=str(raw.get("asset_id", "")),
                        timestamp=str(raw.get("timestamp", "")),
                        action=str(raw.get("action", "")),
                        hook=str(raw.get("hook", "")),
                        music=str(raw.get("music", "")),
                        views=int(raw.get("views", 0) or 0),
                        likes=int(raw.get("likes", 0) or 0),
                    )
                )
    return rows


def build_weighted_marketing_synthesis_prompt(rows: Iterable[MarketingVideoAnalysis]) -> str:
    parts = ["Here are the analyses of marketing videos:\n"]
    row_list = list(rows)
    if not row_list:
        raise ValueError("At least one marketing video analysis row is required.")

    for idx, row in enumerate(row_list, start=1):
        parts.append(f"--- VIDEO {idx}: {row.video_file} ---")
        if row.views > 0 or row.likes > 0:
            parts.append(f"VIEWS: {row.views:,} | LIKES: {row.likes:,}")
        else:
            parts.append("VIEWS: unknown | LIKES: unknown")
        parts.append(f"ACTION: {row.action}")
        parts.append(f"HOOK: {row.hook}")
        parts.append(f"MUSIC: {row.music}")
        parts.append("")
    parts.append(
        "Now synthesize all the above and generate a detailed prompt to create "
        "a new marketing video for a similar product."
    )
    return "\n".join(parts)


async def run_gemini_marketing_synthesis(
    rows: Iterable[MarketingVideoAnalysis],
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    key = (api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY is required for marketing synthesis.")

    resolved_model = model or os.getenv("GEMINI_VIDEO_SYNTHESIS_MODEL", "gemini-2.5-flash")
    user_prompt = build_weighted_marketing_synthesis_prompt(rows)
    client = genai.Client(api_key=key)
    resp = await client.aio.models.generate_content(
        model=resolved_model,
        contents=f"{MARKETING_SYNTHESIS_SYSTEM_PROMPT}\n\n{user_prompt}",
    )
    text = getattr(resp, "text", None) or ""
    return text.strip()


def build_locked_reference_veo_prompt(
    user_prompt: str,
    *,
    system_prompt: str = LOCKED_REFERENCE_VEO_SYSTEM_PROMPT,
) -> str:
    cleaned_user = user_prompt.strip()
    if not cleaned_user:
        raise ValueError("A non-empty user prompt is required.")
    return f"{system_prompt.strip()}\n\nUSER CREATIVE DIRECTION:\n{cleaned_user}"


def build_single_concept_veo_user_prompt_request(
    template: VideoTemplateRecord,
    product: ProductCandidate,
    *,
    product_description: str,
    creative_brief: str,
) -> str:
    payload = {
        "template": template.model_dump(mode="json"),
        "product": product.model_dump(mode="json"),
        "product_description": product_description,
        "creative_brief": creative_brief,
    }
    return f"{SINGLE_CONCEPT_VEO_USER_PROMPT_SYSTEM_PROMPT}\n\nINPUT:\n{json.dumps(payload, indent=2)}"


def build_fallback_veo_user_prompt(
    template: VideoTemplateRecord,
    product: ProductCandidate,
    *,
    product_description: str,
    creative_brief: str,
) -> str:
    product_name = product.title.strip() or "the product"
    inspiration = " ".join(
        part.strip() for part in [template.veo_prompt_draft, creative_brief, product_description] if part
    )
    prompt_parts = [
        f"8-second vertical creator-style reel featuring {product_name}. "
        "Open with a fast tactile hook and confident direct-to-camera energy. "
        "Use warm flattering light, a smooth push-in, and a believable pick-up from a table or shelf. "
        "Keep medium-to-wide framing so the talent, product, and setting stay visible together. "
    ]
    inspiration_excerpt = _limit_words(" ".join(inspiration.split()), max_words=22)
    if inspiration_excerpt:
        prompt_parts.append(f"Inspiration cues: {inspiration_excerpt}. ")
    prompt_parts.append("End on a clean product-forward payoff.")
    return _limit_words("".join(prompt_parts), max_words=75)


def build_veo_prompt_package(
    user_prompt: str,
    *,
    system_prompt: str = LOCKED_REFERENCE_VEO_SYSTEM_PROMPT,
) -> VeoPromptPackage:
    cleaned_system = system_prompt.strip()
    cleaned_user = user_prompt.strip()
    if not cleaned_system:
        raise ValueError("A non-empty system prompt is required.")
    if not cleaned_user:
        raise ValueError("A non-empty user prompt is required.")
    return VeoPromptPackage(
        system_prompt=cleaned_system,
        user_prompt=cleaned_user,
        full_prompt=build_locked_reference_veo_prompt(cleaned_user, system_prompt=cleaned_system),
    )


def write_veo_prompt_package_files(
    *,
    output_dir: str | Path,
    prompt_package: VeoPromptPackage,
) -> VeoPromptPackage:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    system_path = target_dir / "system_prompt.txt"
    user_path = target_dir / "user_prompt.txt"
    full_path = target_dir / "full_prompt.txt"
    system_path.write_text(prompt_package.system_prompt.strip() + "\n", encoding="utf-8")
    user_path.write_text(prompt_package.user_prompt.strip() + "\n", encoding="utf-8")
    full_path.write_text(prompt_package.full_prompt.strip() + "\n", encoding="utf-8")
    return prompt_package.model_copy(
        update={
            "artifact_dir": str(target_dir),
            "system_prompt_path": str(system_path),
            "user_prompt_path": str(user_path),
            "full_prompt_path": str(full_path),
        }
    )


def write_locked_veo_prompt_files(
    *,
    output_dir: str | Path,
    user_prompt: str,
    system_prompt: str = LOCKED_REFERENCE_VEO_SYSTEM_PROMPT,
) -> tuple[Path, Path]:
    prompt_package = build_veo_prompt_package(user_prompt=user_prompt, system_prompt=system_prompt)
    written = write_veo_prompt_package_files(output_dir=output_dir, prompt_package=prompt_package)
    return Path(written.system_prompt_path), Path(written.user_prompt_path)


def export_analysis_json(rows: Iterable[MarketingVideoAnalysis]) -> list[dict[str, object]]:
    return [
        {
            "video_file": row.video_file,
            "asset_id": row.asset_id,
            "timestamp": row.timestamp,
            "action": row.action,
            "hook": row.hook,
            "music": row.music,
            "views": row.views,
            "likes": row.likes,
        }
        for row in rows
    ]


def dump_analysis_json(rows: Iterable[MarketingVideoAnalysis], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(export_analysis_json(rows), indent=2) + "\n", encoding="utf-8")
    return path
