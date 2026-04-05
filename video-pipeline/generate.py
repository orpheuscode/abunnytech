"""
Veo 3.1 Video Generation Pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reads all inputs from the `input/veo/` folder, calls the Veo 3.1 Fast API (default model),
polls until the video is ready, and saves a single file to `output/`
(`veo_<timestamp>.mp4` — vertical 9:16 by default; 8s, or the API’s extended clip when using --extend).

Uses exactly two avatar images (avatar_1, avatar_2 — sorted by filename)
and optionally one product image. With product: 3 reference images.
Without product: 2 reference images (avatars only).

Usage:
    python generate.py              # one 8s clip
    python generate.py --extend     # first 8s seeds extension; only the extended (~16s) clip is saved
    python generate.py -x           # same as --extend

Optional: put custom text in input/veo/extend_prompt.txt for the extension step.
Extend mode does not write the first 8s to disk and removes that clip from API file storage when possible.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

from genai_client import create_genai_client, veo_model_name, vertex_publisher_model

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input" / "veo"
OUTPUT_DIR = ROOT / "output"

SYSTEM_PROMPT_FILE = INPUT_DIR / "system_prompt.txt"
USER_PROMPT_FILE = INPUT_DIR / "user_prompt.txt"
EXTEND_PROMPT_FILE = INPUT_DIR / "extend_prompt.txt"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

POLL_INTERVAL = 10
CLIP_SECONDS = 8
# Veo: "16:9" landscape (horizontal) or "9:16" portrait (vertical).
VIDEO_ASPECT_RATIO = "9:16"

DEFAULT_EXTEND_PROMPT = (
    "Continue this video seamlessly from the final frame. Keep the same characters, "
    "product, lighting, and setting. Natural continuation of motion and story — "
    "no recap, no jump cut to a new scene."
)


def load_text(path: Path) -> str:
    if not path.exists():
        sys.exit(f"[ERROR] Missing required file: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        sys.exit(f"[ERROR] File is empty: {path}")
    return text


def load_extend_prompt() -> str:
    if EXTEND_PROMPT_FILE.exists() and EXTEND_PROMPT_FILE.read_text(encoding="utf-8").strip():
        return EXTEND_PROMPT_FILE.read_text(encoding="utf-8").strip()
    return DEFAULT_EXTEND_PROMPT


def find_two_avatars() -> tuple[Path, Path]:
    avatars = []
    for f in sorted(INPUT_DIR.iterdir()):
        if f.stem.lower().startswith("avatar") and f.suffix.lower() in IMAGE_EXTENSIONS:
            avatars.append(f)
    if len(avatars) < 2:
        sys.exit(
            f"[ERROR] Need at least 2 avatar images in {INPUT_DIR} "
            f"(found {len(avatars)}). Use avatar_1.* and avatar_2.*"
        )
    return avatars[0], avatars[1]


def find_product() -> Path | None:
    for f in INPUT_DIR.iterdir():
        if f.stem.lower() == "product" and f.suffix.lower() in IMAGE_EXTENSIONS:
            return f
    return None


def load_image(path: Path) -> types.Image:
    return types.Image.from_file(location=str(path))


def wait_for_video(client: genai.Client, operation) -> types.GeneratedVideo:
    elapsed = 0
    while not operation.done:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        operation = client.operations.get(operation)
        print(f"[POLL] {elapsed}s elapsed — done={operation.done}")

    resp = operation.response or operation.result
    if not resp or not resp.generated_videos:
        print("\n[ERROR] API returned no video. Full response:")
        print(operation.response or operation.result)
        sys.exit(1)
    return resp.generated_videos[0]


def build_ref_images(avatar_a: Path, avatar_b: Path, product_path: Path | None):
    ref_images = [
        types.VideoGenerationReferenceImage(
            image=load_image(avatar_a),
            reference_type="asset",
        ),
        types.VideoGenerationReferenceImage(
            image=load_image(avatar_b),
            reference_type="asset",
        ),
    ]
    if product_path:
        ref_images.append(
            types.VideoGenerationReferenceImage(
                image=load_image(product_path),
                reference_type="asset",
            )
        )
    return ref_images


def _file_resource_name_for_delete(video: types.Video) -> str | None:
    """Return e.g. files/abc123 for client.files.delete (Gemini Developer API only)."""
    u = (video.uri or "").strip()
    if not u:
        return None
    if u.startswith("files/"):
        return u.split("?", 1)[0]
    if "/files/" in u:
        tail = u.split("/files/", 1)[1]
        fid = tail.split("/")[0].split("?")[0]
        return f"files/{fid}" if fid else None
    return None


def delete_remote_first_clip(client: genai.Client, video: types.Video | None) -> None:
    """Drop the seed clip from API storage; extended output is the only deliverable."""
    if client.vertexai or video is None:
        return
    name = _file_resource_name_for_delete(video)
    if not name:
        return
    try:
        client.files.delete(name=name)
        print("[INFO] Deleted first 8s clip from API storage (only extended video is kept).")
    except Exception as exc:
        print(f"[INFO] Could not delete first-clip API file (safe to ignore): {exc}")


def main():
    parser = argparse.ArgumentParser(description="Veo 3.1 video generation")
    parser.add_argument(
        "--extend",
        "-x",
        action="store_true",
        help="Seed with 8s, extend via API; save only the extended clip (first clip not kept)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Veo 3.1 Fast — Video Generation Pipeline")
    if args.extend:
        print("  Mode: 8s seed + extend (single extended output)")
    else:
        print("  Mode: 8s only")
    print(f"  Aspect: {VIDEO_ASPECT_RATIO} ({'vertical' if VIDEO_ASPECT_RATIO == '9:16' else 'horizontal'})")
    print("=" * 60)

    system_prompt = load_text(SYSTEM_PROMPT_FILE)
    user_prompt = load_text(USER_PROMPT_FILE)
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    avatar_a, avatar_b = find_two_avatars()
    product_path = find_product()

    print(f"\n[OK] System prompt  : {len(system_prompt)} chars")
    print(f"[OK] User prompt    : {len(user_prompt)} chars")
    print(f"[OK] Avatar 1       : {avatar_a.name}")
    print(f"[OK] Avatar 2       : {avatar_b.name}")
    if product_path:
        print(f"[OK] Product image  : {product_path.name}")
    else:
        print("[--] No product image — using 2 avatars only")
    print(f"\n--- Combined prompt (first 200 chars) ---")
    print(full_prompt[:200], "..." if len(full_prompt) > 200 else "")

    ref_images = build_ref_images(avatar_a, avatar_b, product_path)

    client = create_genai_client(ROOT)
    model = veo_model_name()
    if client.vertexai:
        model = vertex_publisher_model(model)
        if not model.startswith("projects/"):
            sys.exit(
                "[ERROR] Vertex AI: set GOOGLE_CLOUD_PROJECT in .env to your GCP "
                "project ID (required for Veo resource path)."
            )
    print(f"\n[SEND] Calling {model} with {len(ref_images)} reference images ({CLIP_SECONDS}s)...")

    operation = client.models.generate_videos(
        model=model,
        prompt=full_prompt,
        config=types.GenerateVideosConfig(
            reference_images=ref_images,
            number_of_videos=1,
            duration_seconds=CLIP_SECONDS,
            aspect_ratio=VIDEO_ASPECT_RATIO,
        ),
    )
    print(f"[WAIT] Operation started: {operation.name}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    gen0 = wait_for_video(client, operation)
    client.files.download(file=gen0.video)

    out_path = OUTPUT_DIR / f"veo_{timestamp}.mp4"

    if not args.extend:
        gen0.video.save(str(out_path))
        print(f"\n{'=' * 60}")
        print(f"  Saved: {out_path}")
        print(f"{'=' * 60}")
        return

    extend_prompt = load_extend_prompt()
    print(f"\n[EXTEND] Prompt ({len(extend_prompt)} chars, first 120): {extend_prompt[:120]}...")

    print(f"[SEND] Extension call on first clip ({CLIP_SECONDS}s follow-up)...")
    op2 = client.models.generate_videos(
        model=model,
        source=types.GenerateVideosSource(
            prompt=extend_prompt,
            video=gen0.video,
        ),
        config=types.GenerateVideosConfig(
            number_of_videos=1,
            duration_seconds=CLIP_SECONDS,
            aspect_ratio=VIDEO_ASPECT_RATIO,
        ),
    )
    print(f"[WAIT] Extension operation: {op2.name}")

    gen1 = wait_for_video(client, op2)
    client.files.download(file=gen1.video)

    # Extended clip is the full deliverable (~16s from API); no merge, no first-clip file on disk.
    gen1.video.save(str(out_path))

    if gen0.video is not None:
        gen0.video.video_bytes = None
    delete_remote_first_clip(client, gen0.video)

    print(f"\n{'=' * 60}")
    print(f"  Saved (extended): {out_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
