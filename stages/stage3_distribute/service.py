from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from packages.contracts.base import Platform, new_id
from packages.contracts.content import ContentPackage
from packages.contracts.distribution import DistributionRecord, DistributionStatus
from packages.contracts.identity import IdentityMatrix, PersonaArchetype
from packages.shared.db import PipelineRecord, get_async_session, log_audit, store_record
from packages.shared.feature_flags import is_dry_run
from stages.stage3_distribute.adapters import (
    BrowserAutomationAdapter,
    CommentReplyAdapter,
    MockBrowserAutomation,
    MockCommentReply,
    MockPlatformPoster,
    PlatformPosterAdapter,
)

log = structlog.get_logger(__name__)

STAGE = "stage3_distribute"
CONTRACT_DISTRIBUTION = "distribution_record"
CONTRACT_CONTENT_PACKAGE = "content_package"
CONTRACT_IDENTITY = "identity_matrix"

# When no thread is stored yet, simulate a small batch of inbound comments.
_DEFAULT_ENGAGEMENT_COMMENTS = (
    "This is so good — how long did this take?",
    "Subscribed! More like this please.",
    "The pacing at the start is *chef's kiss*",
)


def _effective_dry_run(explicit: bool) -> bool:
    return is_dry_run() or explicit


async def _load_pipeline_json(record_id: str) -> dict[str, Any] | None:
    session = await get_async_session()
    async with session:
        result = await session.execute(select(PipelineRecord).where(PipelineRecord.id == record_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return json.loads(row.data)


async def _load_content_package(content_package_id: str) -> ContentPackage | None:
    data = await _load_pipeline_json(content_package_id)
    if data is None:
        return None
    return ContentPackage.model_validate(data)


async def _load_identity(identity_id: str) -> IdentityMatrix | None:
    data = await _load_pipeline_json(identity_id)
    if data is None:
        return None
    return IdentityMatrix.model_validate(data)


async def _list_pipeline_by_contract(contract_type: str, limit: int) -> list[dict[str, Any]]:
    session = await get_async_session()
    async with session:
        result = await session.execute(
            select(PipelineRecord)
            .where(PipelineRecord.contract_type == contract_type)
            .order_by(PipelineRecord.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
    return [json.loads(r.data) for r in rows]


async def _save_distribution_record(record: DistributionRecord) -> None:
    """Insert or replace pipeline row for this distribution record (``store_record`` is insert-only)."""
    payload = record.model_dump(mode="json")
    rid = str(record.id)
    session = await get_async_session()
    async with session:
        existing = await session.get(PipelineRecord, rid)
        if existing is None:
            pass
        else:
            existing.data = json.dumps(payload)
            existing.identity_id = record.identity_id
            existing.updated_at = datetime.now(UTC)
            await session.commit()
            return
    await store_record(CONTRACT_DISTRIBUTION, STAGE, payload, identity_id=record.identity_id)


class DistributionService:
    def __init__(
        self,
        *,
        platform_poster: PlatformPosterAdapter | None = None,
        comment_reply: CommentReplyAdapter | None = None,
        browser_automation: BrowserAutomationAdapter | None = None,
    ) -> None:
        self._platform_poster = platform_poster or MockPlatformPoster()
        self._comment_reply = comment_reply or MockCommentReply()
        self._browser = browser_automation or MockBrowserAutomation()

    async def post_content(
        self,
        content_package_id: str,
        platform: Platform,
        dry_run: bool = True,
    ) -> DistributionRecord:
        dry = _effective_dry_run(dry_run)
        pkg = await _load_content_package(content_package_id)
        if pkg is None:
            stub_id = UUID(content_package_id) if _is_uuid(content_package_id) else new_id()
            pkg = ContentPackage(
                id=stub_id,
                identity_id="unknown",
                blueprint_id="",
                title="[content package not found in store]",
                caption="",
                hashtags=[],
                target_platform=platform,
            )

        caption_preview = (pkg.caption or pkg.title or "").strip()
        hashtags = " ".join(f"#{h.lstrip('#')}" for h in (pkg.hashtags or [])[:12])
        asset_summary = (
            f"{len(pkg.assets)} asset(s)"
            if pkg.assets
            else "no assets attached (metadata-only post body)"
        )

        await log_audit(
            STAGE,
            "distribute_post_requested",
            content_package_id=content_package_id,
            platform=platform.value,
            dry_run=dry,
            title=pkg.title,
            asset_summary=asset_summary,
        )

        if dry:
            log.info(
                "distribute_post_dry_run",
                platform=platform.value,
                content_package_id=content_package_id,
                identity_id=pkg.identity_id,
                would_post_title=pkg.title,
                would_post_caption_preview=caption_preview[:400] + ("…" if len(caption_preview) > 400 else ""),
                would_post_hashtags=hashtags or "(none)",
                would_post_asset_summary=asset_summary,
                ai_disclosure=pkg.ai_disclosure,
            )
            record = DistributionRecord(
                content_package_id=content_package_id,
                identity_id=pkg.identity_id,
                platform=platform,
                post_url=f"https://{platform.value}.example.com/dry-run/{content_package_id[:8]}",
                post_id="",
                status=DistributionStatus.DRY_RUN,
                dry_run=True,
            )
            record.add_audit(
                "dry_run_post_skipped",
                details={
                    "platform": platform.value,
                    "caption_preview": caption_preview[:200],
                    "hashtags": hashtags,
                },
            )
        else:
            record = await self._platform_poster.post(pkg, platform)
            record = record.model_copy(
                update={
                    "dry_run": False,
                    "status": DistributionStatus.POSTED,
                    "content_package_id": content_package_id,
                }
            )
            body = self._compose_post_body(pkg)
            composer_url = f"https://{platform.value}.example.com/create"
            posted = await self._browser.execute_post(composer_url, body)
            if not posted:
                log.warning(
                    "browser_automation_did_not_confirm_post",
                    platform=platform.value,
                    distribution_id=str(record.id),
                )

        await _save_distribution_record(record)
        await log_audit(
            STAGE,
            "distribute_post_completed",
            distribution_record_id=str(record.id),
            status=record.status.value,
            dry_run=record.dry_run,
            platform=platform.value,
        )
        return record

    async def reply_to_comments(
        self,
        distribution_record_id: str,
        identity_id: str,
    ) -> list[str]:
        dist_data = await _load_pipeline_json(distribution_record_id)
        if dist_data is None:
            await log_audit(
                STAGE,
                "distribute_reply_failed",
                reason="distribution_record_not_found",
                distribution_record_id=distribution_record_id,
            )
            log.warning("reply_skipped_missing_distribution", distribution_record_id=distribution_record_id)
            return []

        record = DistributionRecord.model_validate(dist_data)
        identity = await _load_identity(identity_id)
        if identity is None:
            stub_iid = UUID(identity_id) if _is_uuid(identity_id) else new_id()
            identity = IdentityMatrix(
                id=stub_iid,
                name="Creator",
                archetype=PersonaArchetype.ENTERTAINER,
                tagline="",
            )

        dry = is_dry_run()

        await log_audit(
            STAGE,
            "distribute_reply_requested",
            distribution_record_id=distribution_record_id,
            identity_id=identity_id,
            platform=record.platform.value,
            dry_run=dry,
        )

        replies: list[str] = []
        for comment in _DEFAULT_ENGAGEMENT_COMMENTS:
            text = await self._comment_reply.generate_reply(comment, identity)
            replies.append(text)
            if dry:
                log.info(
                    "distribute_reply_dry_run",
                    distribution_record_id=distribution_record_id,
                    inbound_comment=comment,
                    would_reply_preview=text[:240] + ("…" if len(text) > 240 else ""),
                    persona=identity.name,
                    archetype=identity.archetype.value,
                )
            else:
                log.info(
                    "distribute_reply_live_draft",
                    distribution_record_id=distribution_record_id,
                    inbound_comment=comment,
                    reply_preview=text[:240] + ("…" if len(text) > 240 else ""),
                    persona=identity.name,
                )
            record.engagement_reply_count += 1

        record.add_audit(
            "engagement_replies_generated",
            actor="stage3_distribute",
            count=len(replies),
            dry_run=dry,
        )
        await _save_distribution_record(record)
        await log_audit(
            STAGE,
            "distribute_reply_completed",
            distribution_record_id=distribution_record_id,
            replies=len(replies),
            dry_run=dry,
        )
        return replies

    async def get_distribution_status(self, record_id: str) -> DistributionRecord | None:
        data = await _load_pipeline_json(record_id)
        if data is None:
            return None
        return DistributionRecord.model_validate(data)

    async def list_distribution_records(self, limit: int = 100) -> list[DistributionRecord]:
        rows = await _list_pipeline_by_contract(CONTRACT_DISTRIBUTION, limit)
        return [DistributionRecord.model_validate(r) for r in rows]

    def _compose_post_body(self, pkg: ContentPackage) -> str:
        parts = [pkg.title, "", pkg.caption]
        if pkg.hashtags:
            parts.extend(["", " ".join(f"#{h.lstrip('#')}" for h in pkg.hashtags)])
        if pkg.ai_disclosure:
            parts.extend(["", pkg.ai_disclosure])
        return "\n".join(p for p in parts if p is not None).strip()


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    else:
        return True
