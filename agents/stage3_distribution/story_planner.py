from __future__ import annotations

from datetime import datetime

from browser_runtime.audit import get_audit

from .contracts import (
    ContentPackage,
    IdentityMatrix,
    Platform,
    StoryEngagementPlan,
    StorySlide,
)


class StoryPlanner:
    """Creates story engagement plans from ContentPackage + IdentityMatrix."""

    def create_plan(
        self,
        package: ContentPackage,
        platform: Platform,
        identity: IdentityMatrix,
        scheduled_at: datetime | None = None,
        dry_run: bool = True,
    ) -> StoryEngagementPlan:
        slides = [
            self._teaser_slide(package, identity),
            self._poll_slide(package, identity),
            self._cta_slide(package, identity),
        ]
        plan = StoryEngagementPlan(
            package_id=package.package_id,
            platform=platform,
            slides=slides,
            scheduled_at=scheduled_at,
            dry_run=dry_run,
        )
        get_audit().log(
            "story_planner.created",
            {
                "plan_id": plan.plan_id,
                "package_id": package.package_id,
                "platform": platform,
                "slide_count": len(slides),
                "dry_run": dry_run,
            },
        )
        return plan

    def _teaser_slide(self, package: ContentPackage, identity: IdentityMatrix) -> StorySlide:
        content_type = (
            "video" if package.content_type in ("short_video", "reel") else "image"
        )
        caption = (package.caption[:100] + "✨") if package.caption else "✨"
        return StorySlide(
            slide_index=0,
            content_type=content_type,
            caption=caption,
            media_path=package.media_path,
        )

    def _poll_slide(self, package: ContentPackage, identity: IdentityMatrix) -> StorySlide:
        niche = identity.niche.lower()
        if "fashion" in niche or "style" in niche or "outfit" in niche:
            question = "Would you wear this? 🐰"
        elif "food" in niche or "recipe" in niche or "cook" in niche:
            question = "Would you try this? 🐰"
        elif "beauty" in niche or "makeup" in niche or "skin" in niche:
            question = "Would you use this? 🐰"
        elif "fitness" in niche or "workout" in niche or "gym" in niche:
            question = "Would you try this workout? 🐰"
        else:
            question = f"Loving this {identity.niche} content? 🐰"

        return StorySlide(
            slide_index=1,
            content_type="poll",
            poll_question=question,
            poll_options=["Yes! 🔥", "Show me more ✨"],
        )

    def _cta_slide(self, package: ContentPackage, identity: IdentityMatrix) -> StorySlide:
        caption = identity.comment_style.dm_offer_template
        return StorySlide(
            slide_index=2,
            content_type="link_sticker",
            caption=caption,
            cta="DM me for the link!",
        )
