from __future__ import annotations

from typing import Any

import structlog

from packages.contracts.base import Platform, utc_now
from packages.contracts.monetization import (
    BrandOutreachRecord,
    DMConversationRecord,
    ProductCatalogItem,
)
from packages.shared.db import list_pipeline_records, log_audit, store_record
from packages.shared.feature_flags import is_enabled

from .adapters import (
    AttributionAdapter,
    CatalogIngestAdapter,
    MockAttributionAdapter,
    MockCatalogIngest,
    MockOutreachDraftGenerator,
    MockProductScorer,
    MockShopifyAdapter,
    OutreachDraftGenerator,
    ProductScorerAdapter,
    ShopifyAdapter,
)
from .models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStatus,
    ListingDraft,
    OutreachDraft,
)

log = structlog.get_logger(__name__)

STAGE = "stage5_monetize"
FLAG_NAME = "stage5_monetize"
FEATURE_DISABLED_MESSAGE = (
    "Stage 5 monetization is disabled. Set FEATURE_STAGE5_MONETIZE=true to enable."
)

CONTRACT_PRODUCT = "ProductCatalogItem"
CONTRACT_SCORE = "ProductScore"
CONTRACT_LISTING = "ListingDraft"
CONTRACT_OUTREACH = "BrandOutreachRecord"
CONTRACT_OUTREACH_DRAFT = "OutreachDraft"
CONTRACT_DM = "DMConversationRecord"
CONTRACT_ATTRIBUTION = "AttributionRecord"
CONTRACT_APPROVAL = "ApprovalRequest"


def _disabled_result() -> dict[str, Any]:
    return {"ok": False, "message": FEATURE_DISABLED_MESSAGE}


class MonetizeService:
    """Monetization catalog, outreach, attribution, and approval workflows.

    Gated by feature flag. All actions default to draft/dry-run mode.
    Anything purchase- or send-related requires manual approval first.
    """

    def __init__(
        self,
        *,
        scorer: ProductScorerAdapter | None = None,
        catalog_ingest: CatalogIngestAdapter | None = None,
        shopify: ShopifyAdapter | None = None,
        outreach_drafter: OutreachDraftGenerator | None = None,
        attribution: AttributionAdapter | None = None,
    ) -> None:
        self._scorer = scorer or MockProductScorer()
        self._catalog_ingest = catalog_ingest or MockCatalogIngest()
        self._shopify = shopify or MockShopifyAdapter()
        self._outreach_drafter = outreach_drafter or MockOutreachDraftGenerator()
        self._attribution = attribution or MockAttributionAdapter()

    # ------------------------------------------------------------------
    # Product catalog
    # ------------------------------------------------------------------

    async def add_product(
        self,
        identity_id: str,
        name: str,
        price: float = 0.0,
        *,
        description: str = "",
        currency: str = "USD",
        affiliate_url: str = "",
        category: str = "",
        active: bool = True,
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            log.info("stage5_monetize.add_product.skipped", reason="feature_disabled")
            return _disabled_result()

        item = ProductCatalogItem(
            identity_id=identity_id,
            name=name,
            description=description,
            price=price,
            currency=currency,
            affiliate_url=affiliate_url,
            category=category,
            active=active,
        )
        payload = item.model_dump(mode="json")
        await store_record(CONTRACT_PRODUCT, STAGE, payload, identity_id=identity_id)
        await log_audit(
            STAGE, "add_product",
            actor=identity_id, product_id=str(item.id), name=name,
        )
        log.info("stage5_monetize.add_product", product_id=str(item.id), identity_id=identity_id)
        return {"ok": True, "product": payload}

    async def list_products(self, identity_id: str | None = None) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            log.info("stage5_monetize.list_products.skipped", reason="feature_disabled")
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_PRODUCT, STAGE, identity_id=identity_id)
        products: list[dict[str, Any]] = []
        for row in rows:
            try:
                products.append(ProductCatalogItem.model_validate(row).model_dump(mode="json"))
            except Exception:
                log.warning("stage5_monetize.list_products.skip_invalid", record=row.get("id"))

        await log_audit(STAGE, "list_products", actor=identity_id or "system", count=len(products))
        return {"ok": True, "products": products}

    async def ingest_catalog(
        self, source_url: str, identity_id: str
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        items = await self._catalog_ingest.ingest(source_url, identity_id)
        stored: list[dict[str, Any]] = []
        for item in items:
            payload = item.model_dump(mode="json")
            await store_record(CONTRACT_PRODUCT, STAGE, payload, identity_id=identity_id)
            stored.append(payload)

        await log_audit(
            STAGE, "ingest_catalog",
            actor=identity_id, source_url=source_url, count=len(stored),
        )
        log.info("stage5_monetize.ingest_catalog", count=len(stored), source_url=source_url)
        return {"ok": True, "imported": stored}

    # ------------------------------------------------------------------
    # Product scoring
    # ------------------------------------------------------------------

    async def score_product(
        self, product_id: str, identity_id: str
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_PRODUCT, STAGE, identity_id=identity_id)
        product_data = next((r for r in rows if r.get("id") == product_id), None)
        if product_data is None:
            return {"ok": False, "message": f"Product {product_id} not found."}

        product = ProductCatalogItem.model_validate(product_data)
        score = await self._scorer.score(product, identity_id)
        payload = score.model_dump(mode="json")
        await store_record(CONTRACT_SCORE, STAGE, payload, identity_id=identity_id)

        await log_audit(
            STAGE, "score_product",
            actor=identity_id, product_id=product_id, composite=score.composite_score,
        )
        log.info("stage5_monetize.score_product", product_id=product_id, score=score.composite_score)
        return {"ok": True, "score": payload}

    async def score_all_products(self, identity_id: str) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_PRODUCT, STAGE, identity_id=identity_id)
        scores: list[dict[str, Any]] = []
        for row in rows:
            try:
                product = ProductCatalogItem.model_validate(row)
                score = await self._scorer.score(product, identity_id)
                payload = score.model_dump(mode="json")
                await store_record(CONTRACT_SCORE, STAGE, payload, identity_id=identity_id)
                scores.append(payload)
            except Exception:
                log.warning("stage5_monetize.score_all.skip", record=row.get("id"))

        scores.sort(key=lambda s: s.get("composite_score", 0), reverse=True)
        await log_audit(STAGE, "score_all_products", actor=identity_id, count=len(scores))
        return {"ok": True, "scores": scores}

    # ------------------------------------------------------------------
    # Shopify / listing drafts
    # ------------------------------------------------------------------

    async def create_listing_draft(
        self, product_id: str, identity_id: str
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_PRODUCT, STAGE, identity_id=identity_id)
        product_data = next((r for r in rows if r.get("id") == product_id), None)
        if product_data is None:
            return {"ok": False, "message": f"Product {product_id} not found."}

        product = ProductCatalogItem.model_validate(product_data)
        draft = await self._shopify.create_draft_listing(product, identity_id)
        payload = draft.model_dump(mode="json")
        await store_record(CONTRACT_LISTING, STAGE, payload, identity_id=identity_id)

        await log_audit(
            STAGE, "create_listing_draft",
            actor=identity_id, product_id=product_id, draft_id=str(draft.id),
        )
        log.info("stage5_monetize.listing_draft", draft_id=str(draft.id), product_id=product_id)
        return {"ok": True, "draft": payload, "dry_run": draft.dry_run}

    async def list_listing_drafts(self, identity_id: str | None = None) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_LISTING, STAGE, identity_id=identity_id)
        drafts: list[dict[str, Any]] = []
        for row in rows:
            try:
                drafts.append(ListingDraft.model_validate(row).model_dump(mode="json"))
            except Exception:
                log.warning("stage5_monetize.list_drafts.skip_invalid", record=row.get("id"))
        return {"ok": True, "drafts": drafts}

    # ------------------------------------------------------------------
    # Brand outreach
    # ------------------------------------------------------------------

    async def create_outreach(
        self,
        identity_id: str,
        brand_name: str,
        platform: Platform,
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            log.info("stage5_monetize.create_outreach.skipped", reason="feature_disabled")
            return _disabled_result()

        record = BrandOutreachRecord(
            identity_id=identity_id,
            brand_name=brand_name,
            platform=platform,
        )
        payload = record.model_dump(mode="json")
        await store_record(CONTRACT_OUTREACH, STAGE, payload, identity_id=identity_id)
        await log_audit(
            STAGE, "create_outreach",
            actor=identity_id, outreach_id=str(record.id),
            brand_name=brand_name, platform=str(platform),
        )
        log.info("stage5_monetize.create_outreach", outreach_id=str(record.id))
        return {"ok": True, "outreach": payload}

    async def list_outreach(self, identity_id: str | None = None) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            log.info("stage5_monetize.list_outreach.skipped", reason="feature_disabled")
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_OUTREACH, STAGE, identity_id=identity_id)
        records: list[dict[str, Any]] = []
        for row in rows:
            try:
                records.append(BrandOutreachRecord.model_validate(row).model_dump(mode="json"))
            except Exception:
                log.warning("stage5_monetize.list_outreach.skip_invalid", record=row.get("id"))

        await log_audit(STAGE, "list_outreach", actor=identity_id or "system", count=len(records))
        return {"ok": True, "outreach": records}

    async def generate_outreach_draft(
        self,
        outreach_id: str,
        identity_id: str,
        identity_name: str = "Creator",
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_OUTREACH, STAGE, identity_id=identity_id)
        outreach_data = next((r for r in rows if r.get("id") == outreach_id), None)
        if outreach_data is None:
            return {"ok": False, "message": f"Outreach record {outreach_id} not found."}

        outreach = BrandOutreachRecord.model_validate(outreach_data)
        draft = await self._outreach_drafter.generate_draft(outreach, identity_name)
        payload = draft.model_dump(mode="json")
        await store_record(CONTRACT_OUTREACH_DRAFT, STAGE, payload, identity_id=identity_id)

        await log_audit(
            STAGE, "generate_outreach_draft",
            actor=identity_id, outreach_id=outreach_id, draft_id=str(draft.id),
        )
        log.info("stage5_monetize.outreach_draft", draft_id=str(draft.id), brand=outreach.brand_name)
        return {"ok": True, "draft": payload, "dry_run": draft.dry_run}

    async def list_outreach_drafts(self, identity_id: str | None = None) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_OUTREACH_DRAFT, STAGE, identity_id=identity_id)
        drafts: list[dict[str, Any]] = []
        for row in rows:
            try:
                drafts.append(OutreachDraft.model_validate(row).model_dump(mode="json"))
            except Exception:
                log.warning("stage5_monetize.list_outreach_drafts.skip_invalid", record=row.get("id"))
        return {"ok": True, "drafts": drafts}

    # ------------------------------------------------------------------
    # DM logging
    # ------------------------------------------------------------------

    async def log_dm(
        self,
        identity_id: str,
        platform: Platform,
        handle: str,
        message: str,
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            log.info("stage5_monetize.log_dm.skipped", reason="feature_disabled")
            return _disabled_result()

        preview = message if len(message) <= 500 else message[:500]
        record = DMConversationRecord(
            identity_id=identity_id,
            platform=platform,
            counterparty_handle=handle,
            message_preview=preview,
        )
        payload = record.model_dump(mode="json")
        await store_record(CONTRACT_DM, STAGE, payload, identity_id=identity_id)
        await log_audit(
            STAGE, "log_dm",
            actor=identity_id, dm_id=str(record.id),
            platform=str(platform), handle=handle,
        )
        log.info("stage5_monetize.log_dm", dm_id=str(record.id), identity_id=identity_id)
        return {"ok": True, "dm": payload}

    # ------------------------------------------------------------------
    # Attribution (consumes Stage 3/4 data)
    # ------------------------------------------------------------------

    async def compute_attribution(
        self,
        identity_id: str,
        product_id: str,
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        dist_rows = await list_pipeline_records(
            "distribution_record", "stage3_distribute", identity_id=identity_id,
        )
        metric_rows = await list_pipeline_records(
            "PerformanceMetricRecord", "stage4_analyze", identity_id=identity_id,
        )

        record = await self._attribution.compute_attribution(
            identity_id, product_id, dist_rows, metric_rows,
        )
        payload = record.model_dump(mode="json")
        await store_record(CONTRACT_ATTRIBUTION, STAGE, payload, identity_id=identity_id)

        await log_audit(
            STAGE, "compute_attribution",
            actor=identity_id, product_id=product_id,
            distribution_count=len(dist_rows), metric_count=len(metric_rows),
            estimated_revenue=record.estimated_revenue,
        )
        log.info(
            "stage5_monetize.attribution",
            identity_id=identity_id,
            product_id=product_id,
            revenue=record.estimated_revenue,
        )
        return {"ok": True, "attribution": payload}

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------

    async def request_approval(
        self,
        identity_id: str,
        action: ApprovalAction,
        target_id: str,
        description: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        request = ApprovalRequest(
            identity_id=identity_id,
            action=action,
            target_id=target_id,
            description=description,
            context=context or {},
        )
        payload = request.model_dump(mode="json")
        await store_record(CONTRACT_APPROVAL, STAGE, payload, identity_id=identity_id)
        await log_audit(
            STAGE, "request_approval",
            actor=identity_id, approval_id=str(request.id),
            action=action.value, target_id=target_id,
        )
        log.info(
            "stage5_monetize.approval_requested",
            approval_id=str(request.id), action=action.value,
        )
        return {"ok": True, "approval": payload}

    async def review_approval(
        self,
        approval_id: str,
        reviewer: str,
        approved: bool,
        notes: str = "",
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_APPROVAL, STAGE)
        approval_data = next((r for r in rows if r.get("id") == approval_id), None)
        if approval_data is None:
            return {"ok": False, "message": f"Approval request {approval_id} not found."}

        request = ApprovalRequest.model_validate(approval_data)
        if request.status != ApprovalStatus.PENDING:
            return {
                "ok": False,
                "message": f"Approval {approval_id} is already {request.status.value}.",
            }

        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        updated = request.model_copy(update={
            "status": new_status,
            "reviewer": reviewer,
            "reviewed_at": utc_now(),
            "review_notes": notes,
        })
        payload = updated.model_dump(mode="json")
        await store_record(CONTRACT_APPROVAL, STAGE, payload, identity_id=updated.identity_id)

        await log_audit(
            STAGE, "review_approval",
            actor=reviewer, approval_id=approval_id,
            decision="approved" if approved else "rejected",
        )
        log.info(
            "stage5_monetize.approval_reviewed",
            approval_id=approval_id, decision=new_status.value,
        )
        return {"ok": True, "approval": payload}

    async def list_approvals(
        self,
        identity_id: str | None = None,
        status_filter: ApprovalStatus | None = None,
    ) -> dict[str, Any]:
        if not is_enabled(FLAG_NAME):
            return _disabled_result()

        rows = await list_pipeline_records(CONTRACT_APPROVAL, STAGE, identity_id=identity_id)
        approvals: list[dict[str, Any]] = []
        for row in rows:
            try:
                req = ApprovalRequest.model_validate(row)
                if status_filter is not None and req.status != status_filter:
                    continue
                approvals.append(req.model_dump(mode="json"))
            except Exception:
                log.warning("stage5_monetize.list_approvals.skip_invalid", record=row.get("id"))
        return {"ok": True, "approvals": approvals}


monetize_service = MonetizeService()
