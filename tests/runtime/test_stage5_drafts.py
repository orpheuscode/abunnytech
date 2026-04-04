"""Tests for Stage 5 draft generation (listing drafts and outreach drafts)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.contracts.base import Platform
from packages.contracts.monetization import BrandOutreachRecord, ProductCatalogItem
from stages.stage5_monetize.adapters import MockOutreachDraftGenerator, MockShopifyAdapter
from stages.stage5_monetize.models import ListingDraft, ListingDraftStatus, OutreachDraft


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "drafts"


@pytest.fixture
def shopify(tmp_output: Path) -> MockShopifyAdapter:
    return MockShopifyAdapter(output_dir=tmp_output)


@pytest.fixture
def outreach_gen() -> MockOutreachDraftGenerator:
    return MockOutreachDraftGenerator()


@pytest.fixture
def sample_product() -> ProductCatalogItem:
    return ProductCatalogItem(
        identity_id="test-creator-001",
        name="Creator Starter Kit",
        description="Everything to launch your first video series.",
        price=29.99,
        currency="USD",
        category="digital",
        affiliate_url="https://example.com/starter-kit",
    )


@pytest.fixture
def sample_outreach() -> BrandOutreachRecord:
    return BrandOutreachRecord(
        identity_id="test-creator-001",
        brand_name="TechBrand Co",
        platform=Platform.TIKTOK,
    )


class TestMockShopifyAdapter:
    async def test_creates_listing_draft(
        self, shopify: MockShopifyAdapter, sample_product: ProductCatalogItem
    ) -> None:
        draft = await shopify.create_draft_listing(sample_product, "test-creator-001")
        assert isinstance(draft, ListingDraft)
        assert draft.product_id == str(sample_product.id)
        assert draft.identity_id == "test-creator-001"

    async def test_draft_defaults_to_dry_run(
        self, shopify: MockShopifyAdapter, sample_product: ProductCatalogItem
    ) -> None:
        draft = await shopify.create_draft_listing(sample_product, "test-creator-001")
        assert draft.dry_run is True
        assert draft.status == ListingDraftStatus.DRAFT

    async def test_draft_contains_product_info(
        self, shopify: MockShopifyAdapter, sample_product: ProductCatalogItem
    ) -> None:
        draft = await shopify.create_draft_listing(sample_product, "test-creator-001")
        assert draft.title == sample_product.name
        assert draft.price == sample_product.price
        assert draft.currency == sample_product.currency

    async def test_draft_body_html_populated(
        self, shopify: MockShopifyAdapter, sample_product: ProductCatalogItem
    ) -> None:
        draft = await shopify.create_draft_listing(sample_product, "test-creator-001")
        assert sample_product.name in draft.body_html
        assert "$29.99" in draft.body_html

    async def test_draft_written_to_file(
        self, shopify: MockShopifyAdapter, sample_product: ProductCatalogItem, tmp_output: Path
    ) -> None:
        draft = await shopify.create_draft_listing(sample_product, "test-creator-001")
        path = tmp_output / f"listing-{draft.id}.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["product_id"] == str(sample_product.id)

    async def test_draft_tags_include_category(
        self, shopify: MockShopifyAdapter, sample_product: ProductCatalogItem
    ) -> None:
        draft = await shopify.create_draft_listing(sample_product, "test-creator-001")
        assert "digital" in draft.tags
        assert "ai-creator" in draft.tags

    async def test_publish_dry_run_returns_mock_id(
        self, shopify: MockShopifyAdapter, sample_product: ProductCatalogItem
    ) -> None:
        draft = await shopify.create_draft_listing(sample_product, "test-creator-001")
        published = await shopify.publish_listing(draft)
        assert published.status == ListingDraftStatus.PUBLISHED
        assert published.external_listing_id.startswith("mock-shopify-")


class TestMockOutreachDraftGenerator:
    async def test_generates_outreach_draft(
        self, outreach_gen: MockOutreachDraftGenerator, sample_outreach: BrandOutreachRecord
    ) -> None:
        draft = await outreach_gen.generate_draft(sample_outreach, "TestCreator")
        assert isinstance(draft, OutreachDraft)
        assert draft.outreach_record_id == str(sample_outreach.id)
        assert draft.brand_name == "TechBrand Co"

    async def test_draft_defaults_to_dry_run(
        self, outreach_gen: MockOutreachDraftGenerator, sample_outreach: BrandOutreachRecord
    ) -> None:
        draft = await outreach_gen.generate_draft(sample_outreach, "TestCreator")
        assert draft.dry_run is True
        assert draft.status == ListingDraftStatus.DRAFT

    async def test_draft_contains_identity_name(
        self, outreach_gen: MockOutreachDraftGenerator, sample_outreach: BrandOutreachRecord
    ) -> None:
        draft = await outreach_gen.generate_draft(sample_outreach, "TestCreator")
        assert "TestCreator" in draft.body
        assert "TestCreator" in draft.subject

    async def test_draft_contains_brand_name(
        self, outreach_gen: MockOutreachDraftGenerator, sample_outreach: BrandOutreachRecord
    ) -> None:
        draft = await outreach_gen.generate_draft(sample_outreach, "TestCreator")
        assert "TechBrand Co" in draft.body
        assert "TechBrand Co" in draft.subject

    async def test_draft_has_call_to_action(
        self, outreach_gen: MockOutreachDraftGenerator, sample_outreach: BrandOutreachRecord
    ) -> None:
        draft = await outreach_gen.generate_draft(sample_outreach, "TestCreator")
        assert len(draft.call_to_action) > 0

    async def test_draft_references_platform(
        self, outreach_gen: MockOutreachDraftGenerator, sample_outreach: BrandOutreachRecord
    ) -> None:
        draft = await outreach_gen.generate_draft(sample_outreach, "TestCreator")
        assert "tiktok" in draft.body.lower()
        assert draft.platform == Platform.TIKTOK


class TestMockAttribution:
    async def test_attribution_with_metrics(self) -> None:
        from stages.stage5_monetize.adapters import MockAttributionAdapter

        adapter = MockAttributionAdapter()
        dist_rows = [{"id": "dist-001", "platform": "tiktok"}]
        metric_rows = [
            {"metric_type": "views", "value": 1200},
            {"metric_type": "engagement_rate", "value": 3.5},
        ]
        record = await adapter.compute_attribution(
            "test-creator", "prod-001", dist_rows, metric_rows,
        )
        assert record.identity_id == "test-creator"
        assert record.product_id == "prod-001"
        assert record.estimated_revenue > 0
        assert 0.0 <= record.confidence <= 1.0

    async def test_attribution_without_data(self) -> None:
        from stages.stage5_monetize.adapters import MockAttributionAdapter

        adapter = MockAttributionAdapter()
        record = await adapter.compute_attribution("test-creator", "prod-001", [], [])
        assert record.estimated_revenue == 0.0
        assert record.source.value == "organic"
