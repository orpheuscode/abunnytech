"""Stage 4 – Analytics & Directives page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from apps.dashboard.data_loader import load_optimization_directives, load_redo_queue


def render(api_base: str | None) -> None:
    _render_directives(api_base)
    st.markdown("---")
    _render_redo_queue(api_base)


def _render_directives(api_base: str | None) -> None:
    st.markdown("### Optimization Directives")

    directives = load_optimization_directives(api_base)
    if not directives:
        st.info("No optimization directives generated yet.")
        return

    for envelope in directives:
        _directive_card(envelope)


def _directive_card(envelope: dict[str, Any]) -> None:
    items = envelope.get("directives", [])
    confidence = envelope.get("confidence", 0)
    summary = envelope.get("summary", "")

    if summary:
        st.markdown(f"**{summary}**")

    if confidence:
        st.progress(min(confidence, 1.0), text=f"Confidence: {confidence:.0%}")

    if items:
        for d in items:
            dtype = d.get("type", "unknown").replace("_", " ").title()
            priority = d.get("priority", "")
            st.markdown(f"- **{dtype}**" + (f" (priority: {priority})" if priority else ""))
    else:
        st.caption("No individual directives in this envelope.")


def _render_redo_queue(api_base: str | None) -> None:
    st.markdown("### Redo Queue")

    items = load_redo_queue(api_base)
    if not items:
        st.success("Redo queue is empty \u2014 all content passed quality checks.")
        return

    for item in items:
        reason = item.get("reason", "No reason")
        priority = item.get("priority", 0)
        status = item.get("status", "pending")
        target_stage = item.get("target_stage", "?")

        icon = "\U0001f534" if priority >= 1 else "\U0001f7e1"
        st.markdown(
            f"{icon} **{reason}** \u2014 Target stage {target_stage}, "
            f"priority {priority}, status: `{status}`"
        )
