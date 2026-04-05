import sys
import os
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from twelvelabs import TwelveLabs
from twelvelabs.types import VideoContext_AssetId

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_DIR = SCRIPT_DIR / "input" / "videos"
CSV_PATH = SCRIPT_DIR / "results.csv"

PROMPT = (
    "Analyze this video focusing strictly on three things: "
    "1) ACTION - What actions are happening on screen? Describe every movement, "
    "gesture, and physical activity in detail with timestamps. "
    "2) HOOK - What is the hook? How does the video grab attention in the first "
    "few seconds? What makes the viewer want to keep watching? "
    "3) MUSIC - Describe the music and audio. What is the tempo, mood, genre? "
    "How does it complement the visuals and actions?"
)


def ensure_csv():
    if not CSV_PATH.exists():
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["video_file", "asset_id", "timestamp", "action", "hook", "music", "views", "likes"])


def parse_sections(analysis: str) -> tuple[str, str, str]:
    import re
    sections = {"action": "", "hook": "", "music": ""}
    pattern = r"(?:^|\n)\s*\d*\)?\s*(ACTION|HOOK|MUSIC)\s*[:\-]?\s*"
    parts = re.split(pattern, analysis, flags=re.IGNORECASE)
    # parts alternates: [preamble, label, content, label, content, ...]
    for i in range(1, len(parts) - 1, 2):
        label = parts[i].strip().lower()
        content = parts[i + 1].strip()
        if label in sections:
            sections[label] = content
    return sections["action"], sections["hook"], sections["music"]


def append_result(video_file: str, asset_id: str, action: str, hook: str, music: str, views: int = 0, likes: int = 0):
    row = [video_file, asset_id, datetime.now(timezone.utc).isoformat(), action, hook, music, views, likes]
    for attempt in range(5):
        try:
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            return
        except PermissionError:
            print(f"CSV is locked, retrying ({attempt + 1}/5)...")
            time.sleep(2)
    print("Warning: Could not write to CSV. Saving to results_backup.txt instead.")
    with open(SCRIPT_DIR / "results_backup.txt", "a", encoding="utf-8") as f:
        f.write("|".join(row) + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <video_filename>")
        print("  The video file should be in the input/ folder.")
        sys.exit(1)

    video_filename = sys.argv[1]
    video_path = INPUT_DIR / video_filename

    if not video_path.exists():
        print(f"Error: '{video_path}' not found.")
        print(f"Place your video in: {INPUT_DIR}")
        sys.exit(1)

    load_dotenv(SCRIPT_DIR / ".env")
    api_key = os.getenv("TWELVELABS_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        print("Error: Set TWELVELABS_API_KEY in .env")
        sys.exit(1)

    client = TwelveLabs(api_key=api_key)

    print(f"Uploading '{video_filename}'...")
    with open(video_path, "rb") as f:
        asset = client.assets.create(method="direct", file=f)
    print(f"Upload complete. Asset ID: {asset.id}")

    print("Analyzing with Pegasus...")
    video = VideoContext_AssetId(asset_id=asset.id)
    chunks = []
    for text in client.analyze_stream(video=video, prompt=PROMPT):
        if text.event_type == "text_generation":
            print(text.text, end="", flush=True)
            chunks.append(text.text)
    print()

    analysis = "".join(chunks)
    action, hook, music = parse_sections(analysis)

    ensure_csv()
    append_result(video_filename, asset.id, action, hook, music)
    print(f"\nSaved to {CSV_PATH}")


if __name__ == "__main__":
    main()
