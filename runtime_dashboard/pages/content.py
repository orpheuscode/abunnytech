"""Stage 2 – Content Generation page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from runtime_dashboard.data_loader import load_content_packages, load_video_blueprints


def render(api_base: str | None) -> None:
    _render_blueprints(api_base)
    st.markdown("---")
    _render_content_packages(api_base)


def _render_blueprints(api_base: str | None) -> None:
    st.markdown("### Video Blueprints")

    blueprints = load_video_blueprints(api_base)
    if not blueprints:
        st.info("No video blueprints generated yet.")
        return

    for bp in blueprints:
        _blueprint_card(bp)


def _blueprint_card(bp: dict[str, Any]) -> None:
    title = bp.get("title", "Untitled")
    status = bp.get("status", "draft")
    duration = bp.get("duration_seconds", 0)
    fmt = bp.get("format", "unknown")
    script = bp.get("script", "")

    status_color = {"approved": "#00b894", "draft": "#fdcb6e", "rejected": "#d63031"}.get(
        status, "#636e72"
    )

    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-radius:10px; padding:1rem;
                    margin-bottom:0.75rem; border-left:4px solid {status_color};">
            <strong>{title}</strong>
            <span style="float:right; background:{status_color}; color:white;
                        padding:2px 10px; border-radius:12px; font-size:0.8rem;">
                {status}
            </span>
            <br/><span style="color:#636e72;">{duration}s · {fmt}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if script:
        scenes = [s.strip() for s in script.split("\n") if s.strip()]
        with st.expander(f"Script ({len(scenes)} line(s))"):
            for scene in scenes:
                st.markdown(f"- {scene}")


def _render_content_packages(api_base: str | None) -> None:
    st.markdown("### Content Packages")

    packages = load_content_packages(api_base)
    if not packages:
        st.info("No content packages assembled yet.")
        return

    for pkg in packages:
        caption = pkg.get("caption", "")
        platform = pkg.get("platform", "?")
        status = pkg.get("status", "pending")
        hashtags = pkg.get("hashtags", [])

        st.markdown(f"**{caption}**")
        st.caption(
            f"Platform: `{platform}` · Status: `{status}` · "
            f"Tags: {', '.join(hashtags) if hashtags else 'none'}"
        )

        cols = st.columns(2)
        with cols[0]:
            st.caption(f"Video: `{pkg.get('video_url', 'n/a')}`")
        with cols[1]:
            st.caption(f"Thumbnail: `{pkg.get('thumbnail_url', 'n/a')}`")
