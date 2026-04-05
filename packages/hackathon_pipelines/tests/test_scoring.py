from __future__ import annotations

import pytest

from hackathon_pipelines.contracts import ProductCandidate
from hackathon_pipelines.scoring import (
    DEFAULT_PRODUCT_SCORE_WEIGHTS,
    ProductScoreWeights,
    best_product,
    product_score_breakdown,
    rank_products,
    score_product,
)


def make_product(
    product_id: str,
    *,
    visual_marketability: float,
    popularity_signal: float,
    content_potential: float,
    dropship_score: float,
) -> ProductCandidate:
    return ProductCandidate(
        product_id=product_id,
        title=f"Product {product_id}",
        source_url=f"https://example.com/{product_id}",
        visual_marketability=visual_marketability,
        popularity_signal=popularity_signal,
        content_potential=content_potential,
        dropship_score=dropship_score,
    )


def test_score_product_uses_all_four_signals() -> None:
    product = make_product(
        "alpha",
        visual_marketability=1.0,
        popularity_signal=0.5,
        content_potential=0.25,
        dropship_score=0.0,
    )

    score = score_product(product)

    assert score == pytest.approx(0.425)


def test_score_product_normalizes_weights() -> None:
    product = make_product(
        "alpha",
        visual_marketability=0.8,
        popularity_signal=0.6,
        content_potential=0.4,
        dropship_score=0.2,
    )
    custom_weights = ProductScoreWeights(25, 20, 30, 25)

    assert score_product(product, weights=custom_weights) == pytest.approx(
        score_product(product, weights=DEFAULT_PRODUCT_SCORE_WEIGHTS)
    )


def test_product_score_breakdown_reports_weighted_components() -> None:
    product = make_product(
        "alpha",
        visual_marketability=1.0,
        popularity_signal=0.5,
        content_potential=0.25,
        dropship_score=0.0,
    )

    breakdown = product_score_breakdown(product)

    assert breakdown == {
        "visual_marketability": pytest.approx(0.25),
        "popularity_signal": pytest.approx(0.10),
        "content_potential": pytest.approx(0.075),
        "dropship_score": pytest.approx(0.0),
        "score": pytest.approx(0.425),
    }


def test_rank_products_orders_by_score_then_product_id() -> None:
    products = [
        make_product("b", visual_marketability=0.5, popularity_signal=0.5, content_potential=0.5, dropship_score=0.5),
        make_product("a", visual_marketability=0.5, popularity_signal=0.5, content_potential=0.5, dropship_score=0.5),
        make_product("c", visual_marketability=1.0, popularity_signal=0.2, content_potential=0.2, dropship_score=0.2),
    ]

    ranked = rank_products(products)

    assert [product.product_id for product in ranked] == ["a", "b", "c"]


def test_rank_products_respects_custom_weights_and_limit() -> None:
    products = [
        make_product(
            "visual",
            visual_marketability=0.95,
            popularity_signal=0.1,
            content_potential=0.1,
            dropship_score=0.1,
        ),
        make_product(
            "dropship",
            visual_marketability=0.1,
            popularity_signal=0.1,
            content_potential=0.1,
            dropship_score=0.95,
        ),
    ]
    weights = ProductScoreWeights(0.05, 0.05, 0.05, 0.85)

    ranked = rank_products(products, weights=weights, limit=1)

    assert [product.product_id for product in ranked] == ["dropship"]
    assert best_product(products, weights=weights).product_id == "dropship"


def test_rank_products_with_non_positive_limit_returns_empty() -> None:
    products = [
        make_product(
            "alpha",
            visual_marketability=1.0,
            popularity_signal=1.0,
            content_potential=1.0,
            dropship_score=1.0,
        ),
    ]

    assert rank_products(products, limit=0) == []


def test_zero_weight_configuration_is_rejected() -> None:
    product = make_product(
        "alpha",
        visual_marketability=1.0,
        popularity_signal=1.0,
        content_potential=1.0,
        dropship_score=1.0,
    )

    with pytest.raises(ValueError, match="At least one product-scoring weight must be positive"):
        score_product(product, weights=ProductScoreWeights(0.0, 0.0, 0.0, 0.0))
