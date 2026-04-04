"""
demo_dry_run.py — demonstrates all adapter operations in dry-run mode.

No credentials, no network calls, no browser process required.

Run:
    cd packages/browser_runtime
    uv run python ../../examples/browser_runtime/demo_dry_run.py
"""
from __future__ import annotations

import asyncio

from browser_runtime import get_adapter, get_provider
from browser_runtime.session import SessionManager
from browser_runtime.types import (
    AnalyticsFetchRequest,
    CommentReplyRequest,
    DMRequest,
    Platform,
    PostContentRequest,
    TrendingFetchRequest,
)


async def main() -> None:
    print("=" * 60)
    print("browser_runtime  DRY-RUN demo  (MockProvider)")
    print("=" * 60)

    # 1. Create provider and session
    provider = get_provider("mock", dry_run=True)
    mgr = SessionManager()
    session = mgr.create(platform="tiktok", dry_run=True)
    print(f"\n[session] created: {session.session_id}")

    # 2. TikTok — post content
    tiktok = get_adapter("tiktok", provider)
    post_req = PostContentRequest(
        platform=Platform.TIKTOK,
        caption="AI-generated content demo 🤖 | made with #AI #tech",
        hashtags=["AI", "tech", "demo"],
        media_path="./output/demo_video.mp4",
        dry_run=True,
    )
    post_result = await tiktok.post_content(post_req)
    print(f"\n[tiktok] post_content:")
    print(f"  success  : {post_result.success}")
    print(f"  post_id  : {post_result.post_id}")
    print(f"  dry_run  : {post_result.dry_run}")

    # 3. TikTok — reply to comment
    reply_req = CommentReplyRequest(
        platform=Platform.TIKTOK,
        post_id=post_result.post_id or "demo_post",
        comment_id="comment_001",
        reply_text="Thanks for watching! 🙏 (AI-assisted reply)",
        dry_run=True,
    )
    reply_result = await tiktok.reply_to_comment(reply_req)
    print(f"\n[tiktok] reply_to_comment:")
    print(f"  reply_id : {reply_result.reply_id}")

    # 4. Instagram — post content
    instagram = get_adapter("instagram", provider)
    ig_post_req = PostContentRequest(
        platform=Platform.INSTAGRAM,
        caption="Check out this AI-generated Reel! 🎥 #AI",
        media_url="https://cdn.example.com/demo_reel.mp4",
        dry_run=True,
    )
    ig_result = await instagram.post_content(ig_post_req)
    print(f"\n[instagram] post_content:")
    print(f"  post_id  : {ig_result.post_id}")

    # 5. Analytics — fetch metrics
    analytics = get_adapter("analytics", provider)
    analytics_req = AnalyticsFetchRequest(
        platform=Platform.TIKTOK,
        post_id=post_result.post_id or "demo_post",
    )
    metrics = await analytics.fetch_analytics(analytics_req)
    print(f"\n[analytics] fetch_analytics (TikTok):")
    print(f"  views    : {metrics.views:,}")
    print(f"  likes    : {metrics.likes:,}")
    print(f"  comments : {metrics.comments:,}")
    print(f"  shares   : {metrics.shares:,}")
    print(f"  completion_rate: {metrics.completion_rate_pct:.1f}%")

    # 6. Trending audio discovery
    trending_req = TrendingFetchRequest(
        platform=Platform.TIKTOK,
        niche_tags=["tech", "AI"],
        limit=3,
    )
    trending = await tiktok.fetch_trending(trending_req)
    print(f"\n[tiktok] fetch_trending ({len(trending)} items):")
    for item in trending:
        print(f"  - '{item.audio_title}' by {item.audio_author}  "
              f"({item.usage_count:,} uses, +{item.growth_rate_pct:.0f}%)")

    # 7. Cross-platform analytics summary
    summary = await analytics.cross_platform_summary({
        Platform.TIKTOK: "tt_demo_001",
        Platform.INSTAGRAM: "ig_demo_001",
    })
    print(f"\n[analytics] cross_platform_summary:")
    for platform, data in summary.items():
        print(f"  {platform}: {data.views:,} views, {data.likes:,} likes")

    # 8. Teardown
    await mgr.close_all()
    print(f"\n[session] closed  active_sessions={mgr.active_count()}")
    print("\n✓ Dry-run demo complete — zero credentials used.")


if __name__ == "__main__":
    asyncio.run(main())
