from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from pipeline_contracts.models.enums import ProductAvailability


class ProductCatalogItem(BaseModel):
    """Commerce handoff: a product that may be featured in generated content."""

    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., description="Stock keeping unit or stable product key.")
    title: str = Field(..., description="Display title for scripts and captions.")
    price: Decimal | None = Field(
        default=None,
        description="Unit price; JSON may use number or string for precision.",
    )
    currency: str = Field(
        default="USD",
        description="ISO 4217 currency code.",
    )
    url: str | None = Field(
        default=None,
        description="Canonical product or affiliate landing URL.",
    )
    availability: ProductAvailability | None = Field(
        default=None,
        description="Optional stock signal for copy generation.",
    )
