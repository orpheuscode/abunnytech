"""Stage 5 – Monetization / Product Catalog page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from runtime_dashboard.data_loader import _fetch_api, _load_fixture


def render(api_base: str | None) -> None:
    st.info(
        "Stage 5 (Monetization) is **feature-flagged**. "
        "Enable `FEATURE_STAGE5_MONETIZE=true` to activate in production."
    )

    _render_product_catalog(api_base)


def _render_product_catalog(api_base: str | None) -> None:
    st.markdown("### Product Catalog")

    if api_base is None:
        items = _load_fixture("product_catalog")
    else:
        items = _fetch_api(api_base, "/product_catalog")

    if not items:
        st.info("No products in the catalog yet.")
        return

    for prod in items:
        _product_card(prod)


def _product_card(prod: dict[str, Any]) -> None:
    name = prod.get("name", "Unnamed Product")
    description = prod.get("description", "")
    price_cents = prod.get("price_cents", 0)
    url = prod.get("url", "")
    affiliate = prod.get("affiliate_code", "")
    active = prod.get("active", False)

    price_str = f"${price_cents / 100:.2f}"
    status_badge = "\u2705 Active" if active else "\u26d4 Inactive"

    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-radius:10px; padding:1rem;
                    margin-bottom:0.75rem; border-left:4px solid #a29bfe;">
            <strong>{name}</strong> &mdash; {price_str}
            <span style="float:right;">{status_badge}</span>
            <br/><span style="color:#636e72;">{description}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if url:
        st.caption(f"URL: `{url}`")
    if affiliate:
        st.caption(f"Affiliate code: `{affiliate}`")
