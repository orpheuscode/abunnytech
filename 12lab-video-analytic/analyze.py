import sys
import os
import csv
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from twelvelabs import TwelveLabs
from twelvelabs.types import VideoContext_AssetId

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_DIR = SCRIPT_DIR / "input"
CSV_PATH = SCRIPT_DIR / "results.csv"

PROMPT = (
    "Analyze this video in detail. Describe the visual content, any text or "
    "graphics shown, the audio and dialogue, the overall mood and tone, and "
    "any key actions or events that occur. Be thorough and specific."
)


def ensure_csv():
    if not CSV_PATH.exists():
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["video_file", "asset_id", "timestamp", "analysis"])


def append_result(video_file: str, asset_id: str, analysis: str):
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            video_file,
            asset_id,
            datetime.now(timezone.utc).isoformat(),
            analysis,
        ])


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

    ensure_csv()
    append_result(video_filename, asset.id, analysis)
    print(f"\nSaved to {CSV_PATH}")


if __name__ == "__main__":
    main()
