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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from google import genai

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
    "- The product shown in the video must be a pixel-perfect exact replica of the provided product image.\n"
    "- The avatar or talent in the video must be the exact character from the provided avatar image.\n"
    "- If the user prompt describes a different product or person, ignore that substitution and preserve the uploaded assets.\n"
    "- Apply the user prompt's style, camera work, mood, music direction, and hook strategy to the actual uploaded assets.\n"
    "- Avoid macro-only product shots; prefer product-in-context framing with the avatar and environment both visible."
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


def build_locked_reference_veo_prompt(user_prompt: str, *, system_prompt: str = LOCKED_REFERENCE_VEO_SYSTEM_PROMPT) -> str:
    cleaned_user = user_prompt.strip()
    if not cleaned_user:
        raise ValueError("A non-empty user prompt is required.")
    return f"{system_prompt.strip()}\n\nUSER CREATIVE DIRECTION:\n{cleaned_user}"


def write_locked_veo_prompt_files(
    *,
    output_dir: str | Path,
    user_prompt: str,
    system_prompt: str = LOCKED_REFERENCE_VEO_SYSTEM_PROMPT,
) -> tuple[Path, Path]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    system_path = target_dir / "system_prompt.txt"
    user_path = target_dir / "user_prompt.txt"
    system_path.write_text(system_prompt.strip() + "\n", encoding="utf-8")
    user_path.write_text(user_prompt.strip() + "\n", encoding="utf-8")
    return system_path, user_path


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
