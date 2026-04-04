"""Tests for Stage 5 product scoring pipeline."""

from __future__ import annotations

import pytest

from packages.contracts.monetization import ProductCatalogItem
from stages.stage5_monetize.adapters import MockProductScorer
from stages.stage5_monetize.models import ProductScore


@pytest.fixture
def scorer() -> MockProductScorer:
    return MockProductScorer()


@pytest.fixture
def sample_product() -> ProductCatalogItem:
    return ProductCatalogItem(
        identity_id="test-creator-001",
        name="Creator Starter Kit",
        description="Everything to launch your first video series.",
        price=29.99,
        category="digital",
        affiliate_url="https://example.com/starter-kit",
    )


@pytest.fixture
def high_value_product() -> ProductCatalogItem:
    return ProductCatalogItem(
        identity_id="test-creator-001",
        name="Pro Studio Setup",
        description="Full studio equipment bundle.",
        price=199.00,
        category="equipment",
    )


@pytest.fixture
def zero_price_product() -> ProductCatalogItem:
    return ProductCatalogItem(
        identity_id="test-creator-001",
        name="Free Guide PDF",
        description="A free downloadable guide.",
        price=0.0,
        category="lead-magnet",
    )


class TestMockProductScorer:
    async def test_score_returns_product_score(
        self, scorer: MockProductScorer, sample_product: ProductCatalogItem
    ) -> None:
        result = await scorer.score(sample_product, "test-creator-001")
        assert isinstance(result, ProductScore)

    async def test_score_fields_within_bounds(
        self, scorer: MockProductScorer, sample_product: ProductCatalogItem
    ) -> None:
        result = await scorer.score(sample_product, "test-creator-001")
        assert 0.0 <= result.relevance_score <= 1.0
        assert 0.0 <= result.audience_fit_score <= 1.0
        assert 0.0 <= result.margin_score <= 1.0
        assert 0.0 <= result.composite_score <= 1.0

    async def test_score_links_to_product(
        self, scorer: MockProductScorer, sample_product: ProductCatalogItem
    ) -> None:
        result = await scorer.score(sample_product, "test-creator-001")
        assert result.product_id == str(sample_product.id)
        assert result.identity_id == "test-creator-001"

    async def test_score_includes_reasoning(
        self, scorer: MockProductScorer, sample_product: ProductCatalogItem
    ) -> None:
        result = await scorer.score(sample_product, "test-creator-001")
        assert len(result.reasoning) > 0
        assert sample_product.name in result.reasoning

    async def test_deterministic_for_same_product(
        self, scorer: MockProductScorer, sample_product: ProductCatalogItem
    ) -> None:
        s1 = await scorer.score(sample_product, "test-creator-001")
        s2 = await scorer.score(sample_product, "test-creator-001")
        assert s1.composite_score == s2.composite_score

    async def test_high_price_increases_margin_score(
        self,
        scorer: MockProductScorer,
        sample_product: ProductCatalogItem,
        high_value_product: ProductCatalogItem,
    ) -> None:
        low = await scorer.score(sample_product, "test-creator-001")
        high = await scorer.score(high_value_product, "test-creator-001")
        assert high.margin_score >= low.margin_score

    async def test_zero_price_gets_fallback_margin(
        self, scorer: MockProductScorer, zero_price_product: ProductCatalogItem
    ) -> None:
        result = await scorer.score(zero_price_product, "test-creator-001")
        assert result.margin_score == 0.15

    async def test_composite_is_weighted_average(
        self, scorer: MockProductScorer, sample_product: ProductCatalogItem
    ) -> None:
        result = await scorer.score(sample_product, "test-creator-001")
        expected = round(
            result.relevance_score * 0.4
            + result.audience_fit_score * 0.4
            + result.margin_score * 0.2,
            2,
        )
        assert result.composite_score == expected
