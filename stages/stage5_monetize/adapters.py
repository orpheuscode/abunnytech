"""Adapter protocols and mock implementations for Stage 5 monetization.

Follows the same Protocol + Mock pattern used in stages 2–4.
All mocks produce plausible but simulated outputs safe for dry-run demos.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import structlog

from packages.contracts.base import new_id
from packages.contracts.monetization import BrandOutreachRecord, ProductCatalogItem

from .models import (
    AttributionRecord,
    AttributionSource,
    ListingDraft,
    ListingDraftStatus,
    OutreachDraft,
    ProductScore,
)

log = structlog.get_logger(__name__)

OUTPUT_DIR = Path("output/stage5_drafts")


# ---------------------------------------------------------------------------
# Product scoring
# ---------------------------------------------------------------------------

@runtime_checkable
class ProductScorerAdapter(Protocol):
    async def score(
        self, product: ProductCatalogItem, identity_id: str
    ) -> ProductScore:
        """Score a product for relevance, audience fit, and margin."""
        ...


class MockProductScorer:
    """Deterministic scoring based on simple heuristics for demo purposes."""

    async def score(
        self, product: ProductCatalogItem, identity_id: str
    ) -> ProductScore:
        name_hash = int(hashlib.md5(product.name.encode()).hexdigest()[:8], 16)
        relevance = round(0.4 + (name_hash % 60) / 100, 2)
        audience_fit = round(0.3 + ((name_hash >> 8) % 70) / 100, 2)
        margin = round(min(product.price / 200.0, 1.0), 2) if product.price > 0 else 0.15
        composite = round((relevance * 0.4 + audience_fit * 0.4 + margin * 0.2), 2)

        reasoning = (
            f"Product '{product.name}' scored {composite:.2f} composite "
            f"(relevance={relevance}, audience_fit={audience_fit}, margin={margin}). "
            f"{'Strong candidate.' if composite >= 0.6 else 'Below threshold — consider alternatives.'}"
        )

        log.debug(
            "mock_product_scored",
            product_id=str(product.id),
            composite=composite,
        )

        return ProductScore(
            product_id=str(product.id),
            identity_id=identity_id,
            relevance_score=relevance,
            audience_fit_score=audience_fit,
            margin_score=margin,
            composite_score=composite,
            reasoning=reasoning,
        )


# ---------------------------------------------------------------------------
# Catalog ingestion
# ---------------------------------------------------------------------------

@runtime_checkable
class CatalogIngestAdapter(Protocol):
    async def ingest(self, source_url: str, identity_id: str) -> list[ProductCatalogItem]:
        """Pull products from an external source (feed URL, CSV, API)."""
        ...


class MockCatalogIngest:
    """Returns a small set of demo products simulating a feed import."""

    async def ingest(self, source_url: str, identity_id: str) -> list[ProductCatalogItem]:
        log.info("mock_catalog_ingest", source_url=source_url, identity_id=identity_id)
        return [
            ProductCatalogItem(
                identity_id=identity_id,
                name="Creator Starter Kit",
                description="Everything you need to launch your first video series.",
                price=29.99,
                category="digital",
                affiliate_url=f"{source_url}/starter-kit",
            ),
            ProductCatalogItem(
                identity_id=identity_id,
                name="Premium Editing Templates",
                description="50 professional video templates optimized for short-form.",
                price=49.99,
                category="digital",
                affiliate_url=f"{source_url}/templates",
            ),
            ProductCatalogItem(
                identity_id=identity_id,
                name="Ring Light Pro",
                description="Studio-grade ring light with adjustable color temperature.",
                price=89.99,
                category="equipment",
                affiliate_url=f"{source_url}/ring-light",
            ),
        ]


# ---------------------------------------------------------------------------
# Shopify / listing draft adapter
# ---------------------------------------------------------------------------

@runtime_checkable
class ShopifyAdapter(Protocol):
    async def create_draft_listing(
        self, product: ProductCatalogItem, identity_id: str
    ) -> ListingDraft:
        """Generate a store listing draft from a product catalog item."""
        ...

    async def publish_listing(self, draft: ListingDraft) -> ListingDraft:
        """Publish an approved draft to the live store. Requires prior approval."""
        ...


class MockShopifyAdapter:
    """Generates plausible Shopify-style listing drafts written to local files."""

    def __init__(self, *, output_dir: Path = OUTPUT_DIR) -> None:
        self._output_dir = output_dir

    async def create_draft_listing(
        self, product: ProductCatalogItem, identity_id: str
    ) -> ListingDraft:
        draft = ListingDraft(
            product_id=str(product.id),
            identity_id=identity_id,
            title=product.name,
            body_html=self._generate_body_html(product),
            price=product.price,
            currency=product.currency,
            tags=[product.category, "ai-creator", "abunnytech"] if product.category else ["ai-creator"],
            status=ListingDraftStatus.DRAFT,
            dry_run=True,
        )

        self._write_draft_file(draft)
        log.info(
            "mock_shopify_draft_created",
            draft_id=str(draft.id),
            product_id=str(product.id),
            title=product.name,
        )
        return draft

    async def publish_listing(self, draft: ListingDraft) -> ListingDraft:
        if draft.dry_run:
            log.info(
                "mock_shopify_publish_dry_run",
                draft_id=str(draft.id),
                would_publish=draft.title,
            )
            return draft.model_copy(
                update={
                    "external_listing_id": f"mock-shopify-{str(new_id())[:8]}",
                    "status": ListingDraftStatus.PUBLISHED,
                }
            )

        fake_id = f"shopify-{str(new_id())[:8]}"
        log.info(
            "mock_shopify_published",
            draft_id=str(draft.id),
            external_listing_id=fake_id,
        )
        return draft.model_copy(
            update={
                "external_listing_id": fake_id,
                "status": ListingDraftStatus.PUBLISHED,
                "dry_run": False,
            }
        )

    def _generate_body_html(self, product: ProductCatalogItem) -> str:
        return (
            f"<h2>{product.name}</h2>\n"
            f"<p>{product.description or 'No description provided.'}</p>\n"
            f"<p><strong>${product.price:.2f} {product.currency}</strong></p>\n"
            f'<p><a href="{product.affiliate_url}">Learn more</a></p>'
        )

    def _write_draft_file(self, draft: ListingDraft) -> None:
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            path = self._output_dir / f"listing-{draft.id}.json"
            path.write_text(
                json.dumps(draft.model_dump(mode="json"), indent=2, default=str),
                encoding="utf-8",
            )
            log.debug("draft_file_written", path=str(path))
        except OSError:
            log.warning("draft_file_write_failed", draft_id=str(draft.id))


# ---------------------------------------------------------------------------
# Outreach draft generator
# ---------------------------------------------------------------------------

@runtime_checkable
class OutreachDraftGenerator(Protocol):
    async def generate_draft(
        self, outreach: BrandOutreachRecord, identity_name: str
    ) -> OutreachDraft:
        """Produce a templated outreach message draft."""
        ...


class MockOutreachDraftGenerator:
    """Template-based outreach message drafts for brand partnership pitches."""

    async def generate_draft(
        self, outreach: BrandOutreachRecord, identity_name: str
    ) -> OutreachDraft:
        subject = f"Collaboration opportunity — {identity_name} x {outreach.brand_name}"
        body = (
            f"Hi {outreach.brand_name} team,\n\n"
            f"I'm {identity_name}, a content creator on {outreach.platform.value}. "
            f"I've been following your brand and believe there's a strong fit "
            f"for a creative collaboration.\n\n"
            f"My audience is highly engaged in the content space you serve, and I'd love "
            f"to explore a partnership — whether that's a product feature, sponsored series, "
            f"or affiliate arrangement.\n\n"
            f"Would you be open to a brief call this week?\n\n"
            f"Best,\n{identity_name}"
        )
        cta = "Schedule a 15-minute intro call"

        draft = OutreachDraft(
            outreach_record_id=str(outreach.id),
            identity_id=outreach.identity_id,
            brand_name=outreach.brand_name,
            platform=outreach.platform,
            subject=subject,
            body=body,
            call_to_action=cta,
            status=ListingDraftStatus.DRAFT,
            dry_run=True,
        )

        self._write_draft_file(draft)
        log.info(
            "mock_outreach_draft_generated",
            draft_id=str(draft.id),
            brand=outreach.brand_name,
        )
        return draft

    def _write_draft_file(self, draft: OutreachDraft) -> None:
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            path = OUTPUT_DIR / f"outreach-{draft.id}.json"
            path.write_text(
                json.dumps(draft.model_dump(mode="json"), indent=2, default=str),
                encoding="utf-8",
            )
        except OSError:
            log.warning("outreach_draft_file_write_failed", draft_id=str(draft.id))


# ---------------------------------------------------------------------------
# Attribution adapter (consumes Stage 3/4 data)
# ---------------------------------------------------------------------------

@runtime_checkable
class AttributionAdapter(Protocol):
    async def compute_attribution(
        self,
        identity_id: str,
        product_id: str,
        distribution_records: list[dict[str, Any]],
        metrics: list[dict[str, Any]],
    ) -> AttributionRecord:
        """Attribute monetization to upstream distribution and analytics data."""
        ...


class MockAttributionAdapter:
    """Heuristic-based attribution model for demo/dry-run."""

    async def compute_attribution(
        self,
        identity_id: str,
        product_id: str,
        distribution_records: list[dict[str, Any]],
        metrics: list[dict[str, Any]],
    ) -> AttributionRecord:
        total_views = sum(
            m.get("value", 0) for m in metrics if m.get("metric_type") == "views"
        )
        total_engagement = sum(
            m.get("value", 0) for m in metrics if m.get("metric_type") == "engagement_rate"
        )

        dist_id = distribution_records[0].get("id", "") if distribution_records else ""

        source = AttributionSource.DISTRIBUTION if dist_id else AttributionSource.ORGANIC
        estimated_revenue = round(total_views * 0.008 + total_engagement * 2.5, 2)
        confidence = min(0.85, 0.3 + len(distribution_records) * 0.1 + len(metrics) * 0.05)

        record = AttributionRecord(
            identity_id=identity_id,
            product_id=product_id,
            distribution_record_id=dist_id,
            source=source,
            estimated_revenue=estimated_revenue,
            confidence=round(confidence, 2),
            metrics_snapshot={
                "total_views": total_views,
                "total_engagement_rate": total_engagement,
                "distribution_count": len(distribution_records),
                "metric_count": len(metrics),
            },
        )

        log.info(
            "mock_attribution_computed",
            identity_id=identity_id,
            product_id=product_id,
            estimated_revenue=estimated_revenue,
            confidence=record.confidence,
        )
        return record
