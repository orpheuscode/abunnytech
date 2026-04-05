import os
import csv
from pathlib import Path

from dotenv import load_dotenv
from google import genai

SCRIPT_DIR = Path(__file__).resolve().parent
CSV_PATHS = [
    SCRIPT_DIR / "results.csv",
    SCRIPT_DIR / "SocialMediaPipeline.csv",
]
OUTPUT_PATH = SCRIPT_DIR / "Total Analysis Output.txt"

SYSTEM_PROMPT = (
    "You are an expert video marketing strategist and creative director. "
    "You will be given analyses of multiple marketing videos. Each analysis "
    "covers the ACTION (what happens on screen), HOOK (how it grabs attention), "
    "and MUSIC (audio/tempo/mood). Some videos also include VIEWS and LIKES data.\n\n"
    "WEIGHTING RULES:\n"
    "- Videos with higher views and likes are PROVEN performers. Weight their "
    "patterns, techniques, and style MORE heavily in your synthesis.\n"
    "- Videos with 0 views and 0 likes have UNKNOWN performance — not bad, just "
    "no data yet. Still include their patterns normally, but if a conflict arises "
    "between an unknown video and a proven high-performer, favor the proven one.\n"
    "- The higher the views and likes, the more you should borrow from that "
    "video's specific action style, hook strategy, and music choices.\n\n"
    "Your job is to:\n"
    "1) Synthesize patterns across all the videos — what works, what's common, "
    "what makes them effective. Call out which high-performing videos influenced "
    "your decisions most.\n"
    "2) Generate a detailed, production-ready prompt to create a NEW marketing "
    "video for a similar product. The prompt should specify: scene description, "
    "camera movements, talent actions with timestamps, the hook strategy, "
    "music/audio direction, voiceover script, color palette, and mood.\n"
    "Be specific enough that a video production team or AI video generator "
    "could produce the video from your prompt alone."
)


def load_results():
    all_rows = []
    for csv_path in CSV_PATHS:
        if not csv_path.exists():
            print(f"Warning: {csv_path.name} not found, skipping.")
            continue
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            print(f"  Loaded {len(rows)} rows from {csv_path.name}")
            all_rows.extend(rows)

    if not all_rows:
        print("Error: No data found in any CSV. Run analyze.py first.")
        raise SystemExit(1)

    return all_rows


def build_user_prompt(rows):
    parts = ["Here are the analyses of marketing videos:\n"]
    for i, row in enumerate(rows, 1):
        views = int(row.get('views', 0) or 0)
        likes = int(row.get('likes', 0) or 0)
        parts.append(f"--- VIDEO {i}: {row['video_file']} ---")
        if views > 0 or likes > 0:
            parts.append(f"VIEWS: {views:,} | LIKES: {likes:,}")
        else:
            parts.append("VIEWS: unknown | LIKES: unknown")
        parts.append(f"ACTION: {row.get('action', '')}")
        parts.append(f"HOOK: {row.get('hook', '')}")
        parts.append(f"MUSIC: {row.get('music', '')}")
        parts.append("")
    parts.append(
        "Now synthesize all the above and generate a detailed prompt to create "
        "a new marketing video for a similar product."
    )
    return "\n".join(parts)


def main():
    load_dotenv(SCRIPT_DIR / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: Set GEMINI_API_KEY in .env")
        raise SystemExit(1)

    print("Loading video analyses...")
    rows = load_results()
    print(f"Total: {len(rows)} video analyses loaded")

    client = genai.Client(api_key=api_key)
    user_prompt = build_user_prompt(rows)

    print("Sending to Gemini Flash...")
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\n" + user_prompt}]}
        ],
    )

    output = response.text
    print("\n" + output)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"\nSaved to {OUTPUT_PATH}")

    veo_prompt_path = SCRIPT_DIR / "input" / "veo" / "user_prompt.txt"
    with open(veo_prompt_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Also saved to {veo_prompt_path} (ready for generate.py)")


if __name__ == "__main__":
    main()
