"""Reusable scoring helpers for ranked product discovery.

The pipeline stores multiple product-quality signals on ``ProductCandidate``.
This module turns those signals into a single weighted score and provides
deterministic ranking helpers for reuse across product discovery, orchestration,
and any future persistence layer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import fsum

from hackathon_pipelines.contracts import ProductCandidate


@dataclass(frozen=True, slots=True)
class ProductScoreWeights:
    """Weights for the four product-scoring dimensions.

    The weights are normalized before scoring so callers can pass any positive
    scale, e.g. ``1/3`` values, integers, or percentage-like numbers.
    """

    visual_marketability: float = 0.25
    popularity_signal: float = 0.20
    content_potential: float = 0.30
    dropship_score: float = 0.25

    def normalized(self) -> ProductScoreWeights:
        total = fsum(
            (
                self.visual_marketability,
                self.popularity_signal,
                self.content_potential,
                self.dropship_score,
            )
        )
        if total <= 0:
            msg = "At least one product-scoring weight must be positive"
            raise ValueError(msg)
        return ProductScoreWeights(
            visual_marketability=self.visual_marketability / total,
            popularity_signal=self.popularity_signal / total,
            content_potential=self.content_potential / total,
            dropship_score=self.dropship_score / total,
        )


DEFAULT_PRODUCT_SCORE_WEIGHTS = ProductScoreWeights().normalized()


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def score_product(
    product: ProductCandidate,
    *,
    weights: ProductScoreWeights = DEFAULT_PRODUCT_SCORE_WEIGHTS,
) -> float:
    """Return a weighted score in the 0-1 range for a product candidate."""

    w = weights.normalized()
    return fsum(
        (
            _clamp_unit(product.visual_marketability) * w.visual_marketability,
            _clamp_unit(product.popularity_signal) * w.popularity_signal,
            _clamp_unit(product.content_potential) * w.content_potential,
            _clamp_unit(product.dropship_score) * w.dropship_score,
        )
    )


def product_score_breakdown(
    product: ProductCandidate,
    *,
    weights: ProductScoreWeights = DEFAULT_PRODUCT_SCORE_WEIGHTS,
) -> dict[str, float]:
    """Return each weighted contribution plus the final aggregate score."""

    w = weights.normalized()
    contributions = {
        "visual_marketability": _clamp_unit(product.visual_marketability) * w.visual_marketability,
        "popularity_signal": _clamp_unit(product.popularity_signal) * w.popularity_signal,
        "content_potential": _clamp_unit(product.content_potential) * w.content_potential,
        "dropship_score": _clamp_unit(product.dropship_score) * w.dropship_score,
    }
    contributions["score"] = fsum(contributions.values())
    return contributions


def _ranking_key(
    product: ProductCandidate,
    *,
    weights: ProductScoreWeights,
) -> tuple[float, float, float, float, float, str]:
    score = score_product(product, weights=weights)
    return (
        -score,
        -_clamp_unit(product.dropship_score),
        -_clamp_unit(product.content_potential),
        -_clamp_unit(product.popularity_signal),
        -_clamp_unit(product.visual_marketability),
        product.product_id,
    )


def rank_products(
    products: Sequence[ProductCandidate] | Iterable[ProductCandidate],
    *,
    weights: ProductScoreWeights = DEFAULT_PRODUCT_SCORE_WEIGHTS,
    limit: int | None = None,
) -> list[ProductCandidate]:
    """Rank products by weighted score with deterministic tie-breaking."""

    ranked = sorted(products, key=lambda product: _ranking_key(product, weights=weights))
    if limit is None:
        return ranked
    if limit <= 0:
        return []
    return ranked[:limit]


def best_product(
    products: Sequence[ProductCandidate] | Iterable[ProductCandidate],
    *,
    weights: ProductScoreWeights = DEFAULT_PRODUCT_SCORE_WEIGHTS,
) -> ProductCandidate | None:
    """Return the top-ranked product or ``None`` for empty input."""

    ranked = rank_products(products, weights=weights, limit=1)
    return ranked[0] if ranked else None
