import csv
from pathlib import Path

from genai_client import (
    create_genai_client,
    gemini_model_name,
    vertex_publisher_model,
)

SCRIPT_DIR = Path(__file__).resolve().parent
CSV_PATHS = [
    SCRIPT_DIR / "results.csv",
    SCRIPT_DIR / "SocialMediaPipeline.csv",
]
OUTPUT_PATH = SCRIPT_DIR / "Total Analysis Output.txt"

SYSTEM_PROMPT = (
    "ROLE: Expert Video Marketing Strategist & Creative Director.\n"
    "GOAL: Synthesize video performance data into high-converting AI video prompts.\n\n"
    
    "DATA WEIGHTING RULES:\n"
    "- PRIORITIZE: Heavily weight patterns from videos with high Views/Likes (Proven Performers).\n"
    "- NEUTRAL: Treat videos with 0 views/likes as unknown; include patterns but defer to high-performers if styles conflict.\n"
    "- REPLICATE: Borrow the specific HOOK, CAMERA MOVEMENT, and LIGHTING from top performers.\n\n"
    
    "OUTPUT CONSTRAINTS (FOR VEO 3.1 FAST STABILITY):\n"
    "- MAX CONCEPTS: Output exactly TWO (2) video concepts.\n"
    "- PROMPT LENGTH: Keep each 'VEO_PROMPT' under 75 words. Use concrete nouns, not marketing jargon.\n"
    "- TEXT SAFETY: Do NOT describe labels, ingredients, or small text (prevents morphing/hallucination).\n"
    "- VISUAL FOCUS: Describe physical actions, lighting (e.g., 'Cinematic rim light'), and camera paths (e.g., 'Slow push-in').\n\n"
    
    "RESPONSE FORMAT:\n"
    "1. [INTERNAL SYNTHESIS]: 2-sentence summary of which high-performing video influenced the choice.\n"
    "2. [CONCEPT 1]: A creative variation.\n"
    "3. [CONCEPT 2 - THE PROVEN WINNER]: The concept most closely following the top-performing data.\n\n"
    
    "Each concept MUST include a 'VEO_PROMPT' block that can be sent directly to the video generator."
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
    print("Loading video analyses...")
    rows = load_results()
    print(f"Total: {len(rows)} video analyses loaded")

    client = create_genai_client(SCRIPT_DIR)
    model = gemini_model_name()
    if client.vertexai:
        model = vertex_publisher_model(model)
    user_prompt = build_user_prompt(rows)

    print(f"Sending to {model}...")
    response = client.models.generate_content(
        model=model,
        contents=[
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\n" + user_prompt}]}
        ],
    )

    output = response.text

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)
    veo_prompt_path = SCRIPT_DIR / "input" / "veo" / "user_prompt.txt"
    with open(veo_prompt_path, "w", encoding="utf-8") as f:
        f.write(output)

    try:
        print("\n" + output)
    except UnicodeEncodeError:
        print("\n(Console cannot display full Unicode output; see Total Analysis Output.txt)")

    print(f"\nSaved to {OUTPUT_PATH}")
    print(f"Also saved to {veo_prompt_path} (ready for generate.py)")


if __name__ == "__main__":
    main()
