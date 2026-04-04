"""Stage 5 monetization dry-run demo.

Demonstrates creating a product catalog item and a brand outreach record
using the packages.state layer in dry-run mode.
"""

from __future__ import annotations

import asyncio

from packages.state.models import BrandOutreachRecord, ProductCatalogItem
from packages.state.registry import RepositoryRegistry
from packages.state.sqlite import Database


async def main() -> None:
    db = Database(":memory:")
    await db.connect()
    registry = RepositoryRegistry(db)

    await registry.product_catalog._ensure_table()
    await registry.brand_outreach._ensure_table()

    product = ProductCatalogItem(
        name="Creator Toolkit eBook",
        description="The ultimate guide to AI-powered content creation",
        price_cents=1999,
        url="https://store.example.com/creator-toolkit",
        affiliate_code="TECHTOK20",
        active=True,
    )
    await registry.product_catalog.create(product)
    print(f"[Stage 5] Product created: {product.name} (${product.price_cents / 100:.2f})")

    outreach = BrandOutreachRecord(
        brand_name="GadgetCo",
        contact_email="partnerships@gadgetco.example",
        status="lead",
        proposal="Product review series – 3 videos",
        deal_value_cents=250_000,
    )
    await registry.brand_outreach.create(outreach)
    print(f"[Stage 5] Brand outreach: {outreach.brand_name} (${outreach.deal_value_cents / 100:.2f})")

    products = await registry.product_catalog.list_all()
    print(f"\nCatalog has {len(products)} product(s).")

    await db.disconnect()
    print("\nDry-run complete. No real transactions were made.")


if __name__ == "__main__":
    asyncio.run(main())
