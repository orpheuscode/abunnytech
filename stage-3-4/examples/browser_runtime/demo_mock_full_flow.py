"""
demo_mock_full_flow.py — end-to-end pipeline simulation (Stage 3 → Stage 4).

Simulates what Stage 3 (Distribute) and Stage 4 (Analyze) would do,
using only MockProvider.  Suitable for hackathon demo walkthrough.

Run:
    cd packages/browser_runtime
    uv run python ../../examples/browser_runtime/demo_mock_full_flow.py
"""
from __future__ import annotations

import asyncio

from browser_runtime import get_adapter, get_provider
from browser_runtime.audit import get_audit
from browser_runtime.providers.mock import MockProvider
from browser_runtime.types import (
    AgentTask,
    AnalyticsFetchRequest,
    CommentReplyRequest,
    ExtractionSchema,
    Platform,
    PostContentRequest,
    TrendingFetchRequest,
)


async def stage3_distribute(provider: MockProvider) -> dict:
    """Simulate Stage 3: post content to TikTok and Instagram."""
    print("\n── STAGE 3: Distribute & Engage ──")

    tiktok = get_adapter("tiktok", provider)
    instagram = get_adapter("instagram", provider)

    # Post to TikTok
    tt_result = await tiktok.post_content(PostContentRequest(
        platform=Platform.TIKTOK,
        caption="How AI is changing content creation 🤖 #AI #tech #creator",
        hashtags=["AI", "tech", "creator"],
        media_path="./output/video_001.mp4",
        dry_run=False,   # MockProvider handles this as "live" without real network
    ))
    print(f"  [TikTok] posted: {tt_result.post_id}  success={tt_result.success}")

    # Post to Instagram
    ig_result = await instagram.post_content(PostContentRequest(
        platform=Platform.INSTAGRAM,
        caption="AI content pipeline in action 🎬 #AI #innovation",
        media_url="https://cdn.example.com/video_001.mp4",
        dry_run=False,
    ))
    print(f"  [Instagram] posted: {ig_result.post_id}  success={ig_result.success}")

    # Reply to comments (persona-consistent)
    reply_texts = [
        "Great question! The AI writes the script and edits the video end-to-end. 🤖",
        "Thanks for watching! Drop a follow for more AI content 🙏",
    ]
    for i, text in enumerate(reply_texts):
        reply = await tiktok.reply_to_comment(CommentReplyRequest(
            platform=Platform.TIKTOK,
            post_id=tt_result.post_id or "demo",
            comment_id=f"comment_{i:03d}",
            reply_text=text,
            dry_run=False,
        ))
        print(f"  [TikTok] replied to comment_{i:03d}: {reply.reply_id}")

    return {
        "tiktok_post_id": tt_result.post_id,
        "instagram_post_id": ig_result.post_id,
    }


async def stage4_analyze(provider: MockProvider, post_ids: dict) -> None:
    """Simulate Stage 4: collect analytics and run trend discovery."""
    print("\n── STAGE 4: Analyze & Adapt ──")

    analytics = get_adapter("analytics", provider)

    # Fetch metrics across platforms
    summary = await analytics.cross_platform_summary({
        Platform.TIKTOK: post_ids["tiktok_post_id"],
        Platform.INSTAGRAM: post_ids["instagram_post_id"],
    })
    total_views = sum(d.views for d in summary.values())
    total_likes = sum(d.likes for d in summary.values())
    print(f"  [Analytics] total views : {total_views:,}")
    print(f"  [Analytics] total likes : {total_likes:,}")
    for platform, data in summary.items():
        print(f"    {platform:12s}  views={data.views:,}  completion={data.completion_rate_pct:.1f}%")

    # Trend discovery
    tiktok = get_adapter("tiktok", provider)
    trending = await tiktok.fetch_trending(TrendingFetchRequest(
        platform=Platform.TIKTOK,
        niche_tags=["tech", "AI"],
        limit=3,
    ))
    print(f"\n  [Trending] Top {len(trending)} audio tracks:")
    for item in trending:
        print(f"    '{item.audio_title}' — {item.usage_count:,} uses  (+{item.growth_rate_pct:.0f}%)")

    # Bulk extraction demo (CodeAgent style)
    urls = [
        "https://www.tiktok.com/@competitor1/video/001",
        "https://www.tiktok.com/@competitor2/video/002",
    ]
    extractions = await provider.bulk_extract(
        urls,
        ExtractionSchema(
            fields={
                "view_count": "number of views",
                "hook_text": "first 3 seconds of caption",
                "audio_used": "audio track name",
            }
        ),
    )
    print(f"\n  [BulkExtract] Extracted {len(extractions)} competitor videos:")
    for e in extractions:
        print(f"    {e.url[:50]:50s}  success={e.success}")


async def main() -> None:
    print("=" * 60)
    print("browser_runtime  FULL MOCK PIPELINE DEMO")
    print("Stages 3 → 4 using MockProvider (no credentials)")
    print("=" * 60)

    provider = MockProvider(dry_run=False)  # "live" mock

    post_ids = await stage3_distribute(provider)
    await stage4_analyze(provider, post_ids)

    # Show audit log tail
    audit = get_audit()
    entries = audit.tail(10)
    print(f"\n── Audit log (last {len(entries)} entries) ──")
    for entry in entries:
        print(f"  {entry['ts'][:19]}  {entry['level']:7s}  {entry['event']}")

    # Show call inventory
    print(f"\n── MockProvider call counts ──")
    for op, calls in provider.calls.items():
        print(f"  {op}: {len(calls)}")

    print("\n✓ Full mock pipeline demo complete.")


if __name__ == "__main__":
    asyncio.run(main())
