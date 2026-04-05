"""
Veo 3.1 Video Generation Pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reads all inputs from the `input/` folder, calls the real Veo 3.1 API,
polls until the video is ready, and saves it to `output/`.

Usage:
    python generate.py
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parent / ".env")

if not os.environ.get("GEMINI_API_KEY"):
    sys.exit("[ERROR] GEMINI_API_KEY not found. Add it to .env or set it as an environment variable.")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input" / "veo"
OUTPUT_DIR = ROOT / "output"

SYSTEM_PROMPT_FILE = INPUT_DIR / "system_prompt.txt"
USER_PROMPT_FILE = INPUT_DIR / "user_prompt.txt"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

MODEL = "veo-3.1-generate-preview"
POLL_INTERVAL = 10  # seconds between status checks


def load_text(path: Path) -> str:
    if not path.exists():
        sys.exit(f"[ERROR] Missing required file: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        sys.exit(f"[ERROR] File is empty: {path}")
    return text


def find_image(name_stem: str) -> Path:
    """Find an image file by name regardless of extension (jpg, png, webp, etc.)."""
    for f in INPUT_DIR.iterdir():
        if f.stem.lower() == name_stem.lower() and f.suffix.lower() in IMAGE_EXTENSIONS:
            return f
    sys.exit(f"[ERROR] No image found for '{name_stem}' in {INPUT_DIR} (looked for {', '.join(IMAGE_EXTENSIONS)})")


def load_image(path: Path) -> types.Image:
    return types.Image.from_file(location=str(path))


def main():
    # --- 1. Validate inputs ------------------------------------------------
    print("=" * 60)
    print("  Veo 3.1 — Video Generation Pipeline")
    print("=" * 60)

    system_prompt = load_text(SYSTEM_PROMPT_FILE)
    user_prompt = load_text(USER_PROMPT_FILE)
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    product_path = find_image("product")
    avatar_path = find_image("avatar")
    product_img = load_image(product_path)
    avatar_img = load_image(avatar_path)

    print(f"\n[OK] System prompt  : {len(system_prompt)} chars")
    print(f"[OK] User prompt    : {len(user_prompt)} chars")
    print(f"[OK] Product image  : {product_path.name}")
    print(f"[OK] Avatar image   : {avatar_path.name}")
    print(f"\n--- Combined prompt (first 200 chars) ---")
    print(full_prompt[:200], "..." if len(full_prompt) > 200 else "")

    # --- 2. Build reference images -----------------------------------------
    product_ref = types.VideoGenerationReferenceImage(
        image=product_img,
        reference_type="asset",
    )
    avatar_ref = types.VideoGenerationReferenceImage(
        image=avatar_img,
        reference_type="asset",
    )

    # --- 3. Call Veo 3.1 API -----------------------------------------------
    print(f"\n[SEND] Calling {MODEL} ...")
    client = genai.Client()

    operation = client.models.generate_videos(
        model=MODEL,
        prompt=full_prompt,
        config=types.GenerateVideosConfig(
            reference_images=[product_ref, avatar_ref],
            number_of_videos=1,
            duration_seconds=8,
        ),
    )
    print(f"[WAIT] Operation started: {operation.name}")

    # --- 4. Poll until done ------------------------------------------------
    elapsed = 0
    while not operation.done:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        operation = client.operations.get(operation)
        print(f"[POLL] {elapsed}s elapsed — done={operation.done}")

    # --- 5. Download & save ------------------------------------------------
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not operation.response or not operation.response.generated_videos:
        print("\n[ERROR] API returned no video. Full response:")
        print(operation.response)
        sys.exit(1)

    video = operation.response.generated_videos[0]
    client.files.download(file=video.video)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"veo_{timestamp}.mp4"
    video.video.save(str(output_path))

    print(f"\n{'=' * 60}")
    print(f"  Video saved to: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
