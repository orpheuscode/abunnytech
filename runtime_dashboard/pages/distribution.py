"""Stage 3 – Distribution page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from runtime_dashboard.data_loader import load_distribution_records


def render(api_base: str | None) -> None:
    st.markdown("### Distribution Records")

    records = load_distribution_records(api_base)
    if not records:
        st.info("No distribution records yet. Run the pipeline to post content.")
        return

    for rec in records:
        _distribution_card(rec)


def _distribution_card(rec: dict[str, Any]) -> None:
    platform = rec.get("platform", "?")
    status = rec.get("status", "pending")
    post_url = rec.get("post_url", "")
    error_msg = rec.get("error_message", "")
    posted_at = rec.get("posted_at", "")
    dry_run = rec.get("dry_run", False)

    status_map = {
        "posted": ("\u2705", "#00b894"),
        "pending": ("\u23f3", "#fdcb6e"),
        "failed": ("\u274c", "#d63031"),
    }
    icon, color = status_map.get(status, ("\u2753", "#636e72"))

    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-radius:10px; padding:1rem;
                    margin-bottom:0.75rem; border-left:4px solid {color};">
            {icon} <strong>{platform.upper()}</strong> &mdash; {status}
            {"&nbsp; <code>DRY RUN</code>" if dry_run else ""}
            <br/><span style="color:#636e72; font-size:0.85rem;">
                {f'Posted: {posted_at}' if posted_at else 'Not yet posted'}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if post_url:
        st.caption(f"URL: `{post_url}`")

    if error_msg:
        st.error(error_msg)
