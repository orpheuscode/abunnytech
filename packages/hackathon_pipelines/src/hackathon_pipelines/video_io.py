"""Helpers for materializing local video files for generated artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

if TYPE_CHECKING:
    from hackathon_pipelines.contracts import GenerationBundle


def build_output_video_path(*, artifact_id: str, output_dir: str | Path) -> Path:
    """Return a stable local mp4 path for a generated artifact."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{artifact_id}.mp4"


async def download_video_to_path(video_uri: str, output_path: str | Path) -> Path:
    """Download a generated video from a remote URI to a local mp4 path."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
        response = await client.get(video_uri)
        response.raise_for_status()
        target.write_bytes(response.content)
    return target


def render_demo_bundle_video(
    *,
    bundle: GenerationBundle,
    output_path: str | Path,
    fps: int = 12,
    seconds: int = 4,
    canvas_size: tuple[int, int] = (720, 1280),
) -> Path:
    """Render a simple playable mp4 from avatar/product reference images and prompt text."""

    width, height = canvas_size
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    avatar = _load_panel_image(bundle.avatar_image_path, (width, height))
    product = _load_panel_image(bundle.product_image_path, (width, height))
    title = (bundle.product_title or "UGC Demo").strip()
    prompt_lines = _wrap_text(bundle.creative_brief or bundle.veo_prompt, line_length=36)[:4]

    with imageio.get_writer(target, fps=fps, codec="libx264", format="FFMPEG", macro_block_size=16) as writer:
        total_frames = max(fps * seconds, fps)
        for frame_index in range(total_frames):
            frame = _compose_frame(
                avatar=avatar,
                product=product,
                width=width,
                height=height,
                title=title,
                prompt_lines=prompt_lines,
                frame_index=frame_index,
                total_frames=total_frames,
            )
            writer.append_data(frame)
    return target


def build_reference_collage_image(
    *,
    bundle: GenerationBundle,
    output_path: str | Path,
    canvas_size: tuple[int, int] = (1024, 1024),
) -> Path:
    """Build one composite reference image that includes both avatar and product assets."""

    width, height = canvas_size
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    avatar = _load_panel_image(bundle.avatar_image_path, (width, height))
    product = _load_panel_image(bundle.product_image_path, (width, height))

    base = Image.new("RGB", (width, height), color=(18, 18, 24))
    draw = ImageDraw.Draw(base, "RGBA")

    header_height = int(height * 0.16)
    body_height = height - header_height - 36
    left_width = width // 2
    right_width = width - left_width

    avatar_panel = avatar.resize((left_width - 24, body_height), Image.Resampling.LANCZOS)
    product_panel = product.resize((right_width - 24, body_height), Image.Resampling.LANCZOS)
    base.paste(avatar_panel, (12, header_height + 12))
    base.paste(product_panel, (left_width + 12, header_height + 12))

    draw.rounded_rectangle((20, 20, width - 20, header_height), radius=28, fill=(0, 0, 0, 150))
    title = (bundle.product_title or "UGC Reference").strip()[:48]
    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()
    draw.text((40, 42), title, fill=(255, 255, 255), font=title_font)

    prompt_lines = _wrap_text(bundle.creative_brief or bundle.veo_prompt, line_length=52)[:3]
    y = 72
    for line in prompt_lines:
        draw.text((40, y), line, fill=(233, 233, 240), font=body_font)
        y += 24

    draw.rounded_rectangle((28, height - 90, left_width - 28, height - 28), radius=20, fill=(0, 0, 0, 120))
    draw.rounded_rectangle((left_width + 28, height - 90, width - 28, height - 28), radius=20, fill=(0, 0, 0, 120))
    draw.text((48, height - 68), "Avatar reference", fill=(255, 255, 255), font=body_font)
    draw.text((left_width + 48, height - 68), "Product reference", fill=(255, 255, 255), font=body_font)

    base.save(target, format="JPEG", quality=92)
    return target


def _load_panel_image(image_path: str, size: tuple[int, int]) -> Image.Image:
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        image = Image.new("RGB", size, color=(42, 46, 56))
        draw = ImageDraw.Draw(image)
        draw.text((24, 24), Path(image_path).name[:32], fill=(240, 240, 240), font=ImageFont.load_default())
        return image
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)


def _compose_frame(
    *,
    avatar: Image.Image,
    product: Image.Image,
    width: int,
    height: int,
    title: str,
    prompt_lines: list[str],
    frame_index: int,
    total_frames: int,
):
    base = Image.new("RGB", (width, height), color=(18, 18, 24))
    phase = frame_index / max(total_frames - 1, 1)

    avatar_panel = avatar.copy()
    product_panel = product.copy()

    if phase < 0.5:
        avatar_panel = avatar_panel.resize((width, height), Image.Resampling.LANCZOS)
        product_thumb = product_panel.resize((int(width * 0.42), int(height * 0.42)), Image.Resampling.LANCZOS)
        base.paste(avatar_panel, (0, 0))
        base.paste(product_thumb, (width - product_thumb.width - 28, height - product_thumb.height - 180))
    else:
        top_height = height // 2
        avatar_half = avatar_panel.resize((width // 2, top_height), Image.Resampling.LANCZOS)
        product_half = product_panel.resize((width // 2, top_height), Image.Resampling.LANCZOS)
        base.paste(avatar_half, (0, 0))
        base.paste(product_half, (width // 2, 0))
        bottom = product_panel.resize((width, height - top_height), Image.Resampling.LANCZOS)
        base.paste(bottom, (0, top_height))

    draw = ImageDraw.Draw(base, "RGBA")
    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()
    draw.rounded_rectangle((24, 24, width - 24, 208), radius=28, fill=(0, 0, 0, 150))
    draw.text((44, 42), title[:48], fill=(255, 255, 255), font=title_font)

    y = 92
    for line in prompt_lines:
        draw.text((44, y), line, fill=(233, 233, 240), font=body_font)
        y += 30

    progress_width = int((width - 48) * (frame_index + 1) / max(total_frames, 1))
    draw.rounded_rectangle((24, height - 36, width - 24, height - 20), radius=8, fill=(55, 55, 67, 180))
    draw.rounded_rectangle((24, height - 36, 24 + progress_width, height - 20), radius=8, fill=(255, 182, 72, 220))
    return np.asarray(base)


def _wrap_text(text: str, *, line_length: int) -> list[str]:
    words = text.split()
    if not words:
        return ["Prompt unavailable"]
    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        projected = current_len + len(word) + (1 if current else 0)
        if projected > line_length and current:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = projected
    if current:
        lines.append(" ".join(current))
    return lines
