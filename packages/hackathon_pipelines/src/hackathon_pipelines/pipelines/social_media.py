"""Social posting and analytics via Browser Use; closes the loop back to template labels."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from browser_runtime.types import AgentResult, AgentTask
from packages.shared.browser_runtime_config import (
    ENV_CHROME_EXECUTABLE_PATH,
    ENV_CHROME_PROFILE_DIRECTORY,
    ENV_CHROME_USER_DATA_DIR,
)

from hackathon_pipelines.contracts import (
    CommentCategory,
    CommentEngagementPersona,
    CommentEngagementStatus,
    CommentEngagementSummary,
    CommentReplyRecord,
    PostAnalyticsSnapshot,
    PostedContentRecord,
    PostJob,
    TemplatePerformanceLabel,
    VideoTemplateRecord,
)
from hackathon_pipelines.ports import (
    AnalyticsSinkPort,
    BrowserAutomationPort,
    PostedContentSinkPort,
    TemplateStorePort,
)

DEFAULT_ANALYTICS_CHECK_INTERVALS = ("day_1", "day_3", "week_1")
MAX_REPLIES_PER_RUN = 5
PRIORITY_ORDER = [
    CommentCategory.PURCHASE_INTENT,
    CommentCategory.QUESTION,
    CommentCategory.COMPLIMENT,
    CommentCategory.CRITICISM,
    CommentCategory.GENERAL,
]


def _parse_analytics(result: AgentResult) -> PostAnalyticsSnapshot | None:
    out = result.output
    raw = out.get("analytics_json") or out.get("analytics")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    return PostAnalyticsSnapshot(
        snapshot_id=f"snap_{uuid.uuid4().hex[:10]}",
        post_id=str(raw.get("post_id", "unknown")),
        views=int(raw.get("views", 0)),
        likes=int(raw.get("likes", 0)),
        comments=int(raw.get("comments", 0)),
        engagement_trend=raw.get("engagement_trend"),
    )


def _normalize_media_path(media_path: str) -> str:
    return str(Path(media_path).expanduser().resolve())


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.netloc)


def _extract_instagram_post_id(post_ref: str) -> str:
    if not _is_url(post_ref):
        return post_ref
    parts = [part for part in urlparse(post_ref).path.split("/") if part]
    if not parts:
        return post_ref
    if len(parts) >= 2 and parts[0] in {"reel", "reels", "p"}:
        return parts[1]
    return parts[-1]


def _preferred_product_tag(job: PostJob) -> str | None:
    for tag in job.product_tags:
        cleaned = tag.strip()
        if cleaned:
            return cleaned
    return None


def _build_posted_content_record(job: PostJob, *, post_url: str) -> PostedContentRecord:
    return PostedContentRecord(
        post_url=post_url,
        platform=job.platform,
        job_id=job.job_id,
        content_tier=job.content_tier,
        funnel_position=job.funnel_position,
        caption=job.caption,
        hashtags=list(job.hashtags),
        product_name=job.product_name,
        product_tag=_preferred_product_tag(job),
        brand_tags=list(job.brand_tags),
        audio_hook_text=job.audio_hook_text,
        target_niche=job.target_niche,
        thumbnail_text=job.thumbnail_text,
        source_blueprint_id=job.source_blueprint_id,
        analytics_check_intervals=list(DEFAULT_ANALYTICS_CHECK_INTERVALS),
    )


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _comment_signature(commenter_handle: str, comment_text: str) -> str:
    return f"{_collapse_whitespace(commenter_handle).lower()}::{_collapse_whitespace(comment_text).lower()}"


def classify_comment(comment_text: str) -> CommentCategory:
    lowered = (comment_text or "").lower()
    words = set(re.findall(r"[a-zA-Z']+", lowered))
    if any(kw in lowered for kw in ["follow me", "check my", "free money", "click here"]):
        return CommentCategory.SPAM
    if any(kw in lowered for kw in ["where", "buy", "link", "price", "how much", "cost"]):
        return CommentCategory.PURCHASE_INTENT
    if any(kw in lowered for kw in ["doesn't work", "doesnt work", "waste", "bad", "ugly", "fake", "scam"]):
        return CommentCategory.CRITICISM
    if "?" in lowered or any(word in words for word in ["what", "how", "which", "does"]) or "can you" in lowered:
        return CommentCategory.QUESTION
    if any(kw in lowered for kw in ["love", "amazing", "beautiful", "gorgeous", "obsessed", "need"]):
        return CommentCategory.COMPLIMENT
    return CommentCategory.GENERAL


def normalize_comment_engagement_persona(
    persona: CommentEngagementPersona | dict[str, Any] | None,
    *,
    fallback_persona_name: str = "abunnytech",
    fallback_handle: str = "@abunnytech",
) -> CommentEngagementPersona:
    if isinstance(persona, CommentEngagementPersona):
        resolved = persona
    elif isinstance(persona, dict):
        resolved = CommentEngagementPersona.model_validate(persona)
    else:
        resolved = CommentEngagementPersona(
            persona_name=fallback_persona_name,
            instagram_handle=fallback_handle,
        )

    updates: dict[str, Any] = {}
    if not resolved.persona_name.strip():
        updates["persona_name"] = fallback_persona_name

    handle = resolved.instagram_handle.strip()
    if not handle:
        handle = fallback_handle
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"
    if handle != resolved.instagram_handle:
        updates["instagram_handle"] = handle

    if updates:
        resolved = resolved.model_copy(update=updates)
    return resolved


def _response_examples_text(persona: CommentEngagementPersona) -> str:
    if not persona.response_examples:
        return '  [general] Comment: "love this" -> Reply: "ahh thank you so much 🫶"'
    return "\n".join(
        f'  [{key}] Comment: "{example.input}" -> Reply: "{example.output}"'
        for key, example in persona.response_examples.items()
    )


def _build_comment_engagement_prompt(
    post: PostedContentRecord,
    *,
    persona: CommentEngagementPersona,
    already_replied_signatures: set[str],
) -> str:
    priority_text = " > ".join(category.value for category in PRIORITY_ORDER)
    existing_replies_text = "\n".join(f"  - {signature}" for signature in sorted(already_replied_signatures)[:25])
    never_say = ", ".join(persona.never_say) if persona.never_say else "none"
    return f"""You are managing Instagram comments as the account {persona.instagram_handle}.

ACCOUNT VOICE:
- Persona name: {persona.persona_name}
- Tone: {persona.tone}
- Sentence length: {persona.sentence_length}
- Emoji usage: {persona.emoji_usage}
- Capitalization: {persona.capitalization}
- NEVER say: {never_say}

POST CONTEXT:
- Post URL: {post.post_url}
- Product name: {post.product_name or "unknown"}
- Target niche: {post.target_niche or "unknown"}
- Caption: {post.caption or "none"}

RESPONSE EXAMPLES:
{_response_examples_text(persona)}

ALREADY RESPONDED SIGNATURES:
{existing_replies_text or "  - none logged yet"}

FOR THIS POST:
1. Open the Instagram post and scroll to the comments section.
2. Read visible comments.
3. Skip any comment whose signature already appears above.
4. Classify each unresponded comment into exactly one of:
   - purchase_intent
   - question
   - compliment
   - criticism
   - spam
   - general
5. Skip spam entirely.
6. Prioritize replies in this order: {priority_text}
7. Stop after replying to {MAX_REPLIES_PER_RUN} comments total.
8. Reply in lowercase casual style, max 1-2 sentences, with 1-2 emojis max.
9. Use the Instagram Reply button under the comment, then post the reply.
10. Immediately call log_comment_response after each successful reply.
11. If no comments need a response, call no_action_needed once.
12. If Instagram blocks progress or a reply cannot be completed, call report_engagement_failure.

IMPORTANT:
- Never respond to filler comments just to hit the cap.
- Never invent commenter handles, comment text, or replies.
- Never use words from the NEVER say list.
- Only log a reply after it has actually been posted.
"""


def _comment_engagement_summary(
    *,
    replies: list[CommentReplyRecord],
    replies_posted_this_run: int,
    status: CommentEngagementStatus,
    reason: str | None = None,
    error: str | None = None,
) -> CommentEngagementSummary:
    last_reply_at = replies[0].created_at if replies else None
    return CommentEngagementSummary(
        status=status,
        total_replies_logged=len(replies),
        replies_posted_this_run=replies_posted_this_run,
        last_run_at=datetime.now(UTC),
        last_reply_at=last_reply_at,
        last_reason=reason,
        last_error=error,
        recent_replies=list(replies[:3]),
    )


def _build_publish_prompt(job: PostJob, *, video_path: str, thumbnail_path: str | None) -> str:
    caption_for_prompt = job.caption.replace("\n", " [NEWLINE] ")
    brand_tags_str = ", ".join(job.brand_tags) if job.brand_tags else "none"
    thumb_line = (
        f"   - Click 'Edit cover', then use the file picker to open this local file:\n     filepath: {thumbnail_path}"
        if thumbnail_path
        else "   - No cover image to set"
    )

    return f"""You are posting a reel to Instagram. You are already logged in.

STEPS:
1. Click the "+" (Create) button in the Instagram navigation
2. Select "Reel" from the options
3. Use the file upload button (do not navigate to any URL). The local video file path is:
   filepath: {video_path}
4. Wait for the video to process/upload completely
5. Type this EXACT caption into the caption field. Where you see [NEWLINE], press
   Shift+Enter to insert a real line break — do NOT type the word "[NEWLINE]":
   ---
   {caption_for_prompt}
   ---
6. If there are accounts to tag on the video:
   - Click "Tag people"
   - Search for and tag: {brand_tags_str}
7. Cover image:
{thumb_line}
8. Click "Share" or "Post" to publish the reel
9. Wait for the post to go live
10. Read the post URL from the address bar
11. Call save_post with:
    - post_url: the URL from the address bar
    - content_tier: {job.content_tier}
    - caption: the caption text above
    - product_name: {job.product_name}
    - audio_hook_text: {job.audio_hook_text}
    - target_niche: {job.target_niche}
    - funnel_position: {job.funnel_position}
    - source_blueprint_id: {job.source_blueprint_id}

IMPORTANT:
- Do NOT modify the caption in any way — paste it exactly as provided
- If a tag account is not found, skip it and continue
- If the upload gets stuck, wait up to 30 seconds before retrying
- Call save_post IMMEDIATELY after the post goes live
- If anything fails, call report_failure with the reason and step name
"""


def _build_isolated_local_browser_override(
    browser_runtime_env: Mapping[str, str] | None,
) -> dict[str, Any] | None:
    if not browser_runtime_env:
        return None
    executable_path = str(browser_runtime_env.get(ENV_CHROME_EXECUTABLE_PATH) or "").strip()
    user_data_dir = str(browser_runtime_env.get(ENV_CHROME_USER_DATA_DIR) or "").strip()
    profile_directory = str(browser_runtime_env.get(ENV_CHROME_PROFILE_DIRECTORY) or "").strip()
    if not (executable_path and user_data_dir and profile_directory):
        return None
    return {
        "cdp_url": None,
        "headless": False,
        "keep_alive": False,
        "isolate_local_browser_profile": True,
        "executable_path": executable_path,
        "user_data_dir": user_data_dir,
        "profile_directory": profile_directory,
        "extra_kwargs": {
            "enable_default_extensions": False,
        },
    }


def _generate_thumbnail_text_overlay(
    image_path: str,
    text: str,
    output_path: str,
    *,
    font_size: int = 96,
    position: str = "center",
) -> str:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    img_width, img_height = img.size
    x = (img_width - text_width) // 2
    if position == "top":
        y = img_height // 6
    elif position == "bottom":
        y = img_height - text_height - (img_height // 6)
    else:
        y = (img_height - text_height) // 2

    draw.text(
        (x, y),
        text,
        font=font,
        fill="white",
        stroke_width=3,
        stroke_fill="black",
    )
    img.save(output_path)
    return output_path


def _maybe_generate_thumbnail(video_path: str, thumbnail_text: str) -> str | None:
    text = thumbnail_text.strip()
    if not text:
        return None

    output_dir = Path("output") / "hackathon_thumbnails"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"thumb_{Path(video_path).stem}.jpg"

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:01", "-frames:v", "1", str(output_path)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("ffmpeg failed to extract thumbnail frame")
    except Exception:
        from PIL import Image

        Image.new("RGB", (1080, 1920), color=(0, 0, 0)).save(output_path)

    return _generate_thumbnail_text_overlay(
        image_path=str(output_path),
        text=text,
        output_path=str(output_path),
    )


def _prepare_instagram_reel_upload(video_path: str) -> str:
    source_path = Path(video_path).expanduser().resolve()
    output_dir = Path("output") / "hackathon_upload_ready"
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = output_dir / f"{source_path.stem}.instagram.mp4"

    try:
        if prepared_path.exists() and prepared_path.stat().st_mtime >= source_path.stat().st_mtime:
            return str(prepared_path.resolve())
    except OSError:
        pass

    filter_graph = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1"
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source_path),
                "-vf",
                filter_graph,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(prepared_path),
            ],
            capture_output=True,
            timeout=180,
            check=False,
        )
        if result.returncode == 0 and prepared_path.exists():
            return str(prepared_path.resolve())
    except Exception:
        pass
    return str(source_path)


def _build_browser_use_tools(
    job: PostJob,
    *,
    posted_content_sink: PostedContentSinkPort,
) -> tuple[Any | None, list[str]]:
    try:
        import browser_use

        tools = browser_use.Tools()
        action_result_cls = getattr(browser_use, "ActionResult", None)
    except Exception:
        return None, []

    saved_urls: list[str] = []

    def _tool_result(message: str, *, success: bool = True, is_done: bool = False) -> Any:
        if action_result_cls is None:
            return message
        return action_result_cls(
            extracted_content=message,
            is_done=is_done,
            success=success,
        )

    @tools.action(description="Save a successfully posted reel. Call immediately after posting.")
    def save_post(
        post_url: str,
        content_tier: str = "",
        caption: str = "",
        product_name: str = "",
        audio_hook_text: str = "",
        target_niche: str = "",
        funnel_position: str = "",
        source_blueprint_id: str = "",
    ) -> str:
        updated_job = job.model_copy(
            update={
                "content_tier": content_tier or job.content_tier,
                "caption": caption or job.caption,
                "product_name": product_name or job.product_name,
                "audio_hook_text": audio_hook_text or job.audio_hook_text,
                "target_niche": target_niche or job.target_niche,
                "funnel_position": funnel_position or job.funnel_position,
                "source_blueprint_id": source_blueprint_id or job.source_blueprint_id,
            }
        )
        posted_content_sink.persist_posted_content(_build_posted_content_record(updated_job, post_url=post_url))
        saved_urls.append(post_url)
        return _tool_result(
            (
                f"POST SAVED: {post_url} | Tier: {updated_job.content_tier} | "
                "Analytics scheduled for day_1, day_3, week_1"
            ),
            is_done=True,
        )

    @tools.action(description="Report a posting failure with reason and step that failed.")
    def report_failure(reason: str, step_failed: str = "") -> str:
        return _tool_result(
            f"POSTING FAILED at step '{step_failed}': {reason}",
            success=False,
            is_done=True,
        )

    return tools, saved_urls


def _coerce_comment_category(value: str, *, comment_text: str) -> CommentCategory:
    normalized = (value or "").strip().lower().replace(" ", "_")
    for category in CommentCategory:
        if normalized == category.value:
            return category
    return classify_comment(comment_text)


def _build_comment_engagement_tools(
    post: PostedContentRecord,
    *,
    posted_content_sink: PostedContentSinkPort,
    existing_signatures: set[str],
    run_id: str | None,
) -> tuple[Any | None, dict[str, Any]]:
    try:
        import browser_use

        tools = browser_use.Tools()
        action_result_cls = getattr(browser_use, "ActionResult", None)
    except Exception:
        return None, {
            "logged_replies": [],
            "no_action_reason": "",
            "no_action_called": False,
            "failure_reason": "",
        }

    state: dict[str, Any] = {
        "logged_replies": [],
        "no_action_reason": "",
        "no_action_called": False,
        "failure_reason": "",
    }

    def _tool_result(message: str, *, success: bool = True, is_done: bool = False) -> Any:
        if action_result_cls is None:
            return message
        return action_result_cls(
            extracted_content=message,
            is_done=is_done,
            success=success,
        )

    @tools.action(
        description="Save a posted Instagram reply immediately after it is visible on the page.",
    )
    def log_comment_response(
        commenter_handle: str = "",
        comment_text: str = "",
        comment_type: str = "",
        response_text: str = "",
        dm_triggered: int = 0,
    ) -> str:
        signature = _comment_signature(commenter_handle, comment_text)
        if signature in existing_signatures:
            return f"SKIPPED DUPLICATE: {signature}"

        reply = CommentReplyRecord(
            reply_id=f"reply_{uuid.uuid4().hex[:12]}",
            post_url=post.post_url,
            post_id=_extract_instagram_post_id(post.post_url),
            run_id=run_id,
            commenter_handle=_collapse_whitespace(commenter_handle),
            comment_text=_collapse_whitespace(comment_text),
            comment_signature=signature,
            comment_category=_coerce_comment_category(comment_type, comment_text=comment_text),
            response_text=_collapse_whitespace(response_text),
            dm_triggered=bool(dm_triggered),
        )
        posted_content_sink.persist_comment_reply(reply)
        existing_signatures.add(signature)
        state["logged_replies"].append(reply)
        return _tool_result(f"LOGGED: reply to @{reply.commenter_handle or 'unknown'} on {post.post_url}")

    @tools.action(description="Report that no visible comments needed a response on this post.")
    def no_action_needed(reason: str = "") -> str:
        state["no_action_called"] = True
        state["no_action_reason"] = _collapse_whitespace(reason)
        return _tool_result(
            f"NO ACTION: {post.post_url} - {state['no_action_reason'] or 'no comments needed a response'}",
            is_done=True,
        )

    @tools.action(description="Report an engagement failure if Instagram blocks the reply flow.")
    def report_engagement_failure(reason: str, step_failed: str = "") -> str:
        pieces = [piece for piece in [_collapse_whitespace(step_failed), _collapse_whitespace(reason)] if piece]
        state["failure_reason"] = " - ".join(pieces) if pieces else "Unknown engagement failure"
        return _tool_result(
            f"ENGAGEMENT FAILED: {state['failure_reason']}",
            success=False,
            is_done=True,
        )

    return tools, state


class SocialMediaPipeline:
    def __init__(
        self,
        *,
        browser: BrowserAutomationPort,
        analytics_sink: AnalyticsSinkPort,
        posted_content_sink: PostedContentSinkPort,
        templates: TemplateStorePort,
        browser_runtime_env: Mapping[str, str] | None = None,
    ) -> None:
        self._browser = browser
        self._analytics = analytics_sink
        self._posted_content = posted_content_sink
        self._templates = templates
        self._browser_runtime_env = dict(browser_runtime_env or {})

    async def publish_reel(self, job: PostJob) -> AgentResult:
        resolved_media_path = _normalize_media_path(job.media_path)
        upload_media_path = _prepare_instagram_reel_upload(resolved_media_path)
        thumbnail_path = _maybe_generate_thumbnail(upload_media_path, job.thumbnail_text)
        resolved_thumbnail_path = _normalize_media_path(thumbnail_path) if thumbnail_path is not None else None
        if job.dry_run:
            tools, saved_urls = None, []
        else:
            tools, saved_urls = _build_browser_use_tools(job, posted_content_sink=self._posted_content)

        available_file_paths = [upload_media_path]
        if resolved_thumbnail_path is not None:
            available_file_paths.append(resolved_thumbnail_path)

        task = AgentTask(
            description=_build_publish_prompt(
                job,
                video_path=upload_media_path,
                thumbnail_path=resolved_thumbnail_path,
            ),
            max_steps=35,
            dry_run=job.dry_run,
            metadata={
                "pipeline": "social_publish",
                "job_id": job.job_id,
                "browser_use": {
                    "use_vision": True,
                    "vision_detail_level": "high",
                    "step_timeout": 180,
                    "llm_timeout": 120,
                    "max_actions_per_step": 4,
                    "directly_open_url": False,
                    "extend_system_message": (
                        "Call save_post immediately after the Instagram reel goes live. "
                        "Do not invent a post URL. "
                        "Ignore any local file path that looks URL-like and never navigate to it. "
                        "If Instagram shows an Aw, Snap crash page, reload Instagram "
                        "and continue from the current step."
                    ),
                },
                "browser_use_tools": tools,
                "browser_use_browser": _build_isolated_local_browser_override(self._browser_runtime_env),
                "browser_use_agent_kwargs": {
                    "available_file_paths": available_file_paths,
                },
            },
        )
        result = await self._browser.run_task(task)
        output = dict(result.output)
        if saved_urls and not output.get("post_url"):
            output["post_url"] = saved_urls[0]
        if output.get("post_url") and not output.get("post_id"):
            output["post_id"] = _extract_instagram_post_id(str(output["post_url"]))
        post_url = str(output.get("post_url") or "")
        if post_url and self._posted_content.get_posted_content(post_url) is None:
            self._posted_content.persist_posted_content(_build_posted_content_record(job, post_url=post_url))
        return result.model_copy(update={"output": output})

    async def engage_post_comments(
        self,
        post_url: str,
        *,
        persona: CommentEngagementPersona | dict[str, Any] | None,
        dry_run: bool = False,
        run_id: str | None = None,
    ) -> CommentEngagementSummary:
        post = self._posted_content.get_posted_content(post_url)
        if post is None:
            return _comment_engagement_summary(
                replies=[],
                replies_posted_this_run=0,
                status=CommentEngagementStatus.FAILED,
                error=f"Posted content record not found for {post_url}",
            )

        resolved_persona = normalize_comment_engagement_persona(
            persona,
            fallback_persona_name=post.product_name or "abunnytech",
            fallback_handle="@abunnytech",
        )
        existing_replies = self._posted_content.list_comment_replies(post_url)
        existing_signatures = {
            reply.comment_signature or _comment_signature(reply.commenter_handle, reply.comment_text)
            for reply in existing_replies
        }

        if dry_run:
            summary = _comment_engagement_summary(
                replies=existing_replies,
                replies_posted_this_run=0,
                status=CommentEngagementStatus.SKIPPED,
                reason="dry_run_preview",
            )
            self._posted_content.update_posted_content_engagement(post_url, summary)
            return summary

        tools, state = _build_comment_engagement_tools(
            post,
            posted_content_sink=self._posted_content,
            existing_signatures=existing_signatures,
            run_id=run_id,
        )
        task = AgentTask(
            description=_build_comment_engagement_prompt(
                post,
                persona=resolved_persona,
                already_replied_signatures=existing_signatures,
            ),
            url=post.post_url,
            max_steps=35,
            dry_run=False,
            metadata={
                "pipeline": "social_comment_engagement",
                "post_url": post.post_url,
                "post_id": _extract_instagram_post_id(post.post_url),
                "browser_use": {
                    "use_vision": True,
                    "vision_detail_level": "high",
                    "step_timeout": 180,
                    "llm_timeout": 120,
                    "max_actions_per_step": 4,
                    "extend_system_message": (
                        "Engage with Instagram comments carefully. "
                        "Never double-reply to the same handle and comment text. "
                        "Log each posted reply immediately after it appears."
                    ),
                },
                "browser_use_tools": tools,
                "browser_use_browser": _build_isolated_local_browser_override(self._browser_runtime_env),
            },
        )

        try:
            result = await self._browser.run_task(task)
        except Exception as exc:
            summary = _comment_engagement_summary(
                replies=self._posted_content.list_comment_replies(post_url),
                replies_posted_this_run=len(state["logged_replies"]),
                status=CommentEngagementStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
            self._posted_content.update_posted_content_engagement(post_url, summary)
            return summary

        replies = self._posted_content.list_comment_replies(post_url)
        failure_reason = _collapse_whitespace(
            str(state.get("failure_reason") or result.error or result.output.get("error") or "")
        )
        if failure_reason or not result.success:
            summary = _comment_engagement_summary(
                replies=replies,
                replies_posted_this_run=len(state["logged_replies"]),
                status=CommentEngagementStatus.FAILED,
                error=failure_reason or "Instagram comment engagement did not complete successfully.",
            )
        elif state["logged_replies"]:
            summary = _comment_engagement_summary(
                replies=replies,
                replies_posted_this_run=len(state["logged_replies"]),
                status=CommentEngagementStatus.REPLIED,
                reason="replies_posted",
            )
        elif state["no_action_called"]:
            summary = _comment_engagement_summary(
                replies=replies,
                replies_posted_this_run=0,
                status=CommentEngagementStatus.NO_ACTION_NEEDED,
                reason=state["no_action_reason"] or "no comments needed a response",
            )
        else:
            summary = _comment_engagement_summary(
                replies=replies,
                replies_posted_this_run=0,
                status=CommentEngagementStatus.SKIPPED,
                reason="no replies were logged",
            )

        self._posted_content.update_posted_content_engagement(post_url, summary)
        return summary

    async def fetch_post_analytics(self, post_id: str, *, dry_run: bool = True) -> PostAnalyticsSnapshot:
        post_ref = post_id
        task = AgentTask(
            description=(
                "Open Instagram insights for this reel. Read views, likes, comments, and a short trend note. "
                'Respond JSON only: {"post_id":"...","views":0,"likes":0,"comments":0,"engagement_trend":"..."}'
            ),
            url=post_ref if _is_url(post_ref) else None,
            max_steps=25,
            dry_run=dry_run,
            metadata={
                "pipeline": "social_analytics",
                "post_id": post_ref,
                "browser_use": {
                    "use_vision": True,
                    "vision_detail_level": "high",
                    "step_timeout": 120,
                    "llm_timeout": 90,
                },
            },
        )
        result = await self._browser.run_task(task)
        snap = _parse_analytics(result)
        if snap:
            self._analytics.persist_post_analytics(snap)
            return snap
        fallback = PostAnalyticsSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:10]}",
            post_id=_extract_instagram_post_id(post_ref),
            views=10_000 if result.dry_run else 0,
            likes=400 if result.dry_run else 0,
            comments=40 if result.dry_run else 0,
            engagement_trend="dry_run_flat" if result.dry_run else None,
        )
        self._analytics.persist_post_analytics(fallback)
        return fallback

    def apply_performance_to_template(
        self,
        template: VideoTemplateRecord,
        snapshot: PostAnalyticsSnapshot,
        *,
        strong_views: int = 50_000,
        weak_views: int = 2_000,
    ) -> VideoTemplateRecord:
        if snapshot.views >= strong_views and snapshot.likes >= max(500, snapshot.views // 200):
            label = TemplatePerformanceLabel.SUCCESSFUL_REUSE
        elif snapshot.views >= weak_views:
            label = TemplatePerformanceLabel.REMIXABLE
        else:
            label = TemplatePerformanceLabel.WEAK_DISCARD
        updated = template.model_copy(update={"performance_label": label})
        self._templates.update_template(updated)
        return updated
