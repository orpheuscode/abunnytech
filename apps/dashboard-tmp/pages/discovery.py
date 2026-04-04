"""Stage 1 – Discovery Queue page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from apps.dashboard.data_loader import load_trending_audio


def render(api_base: str | None) -> None:
    _render_trending_audio(api_base)
    st.markdown("---")
    _render_competitor_watch(api_base)


def _render_trending_audio(api_base: str | None) -> None:
    st.markdown("### Trending Audio")

    items = load_trending_audio(api_base)
    if not items:
        st.info("No trending audio discovered yet.")
        return

    for item in items:
        _audio_card(item)


def _audio_card(item: dict[str, Any]) -> None:
    title = item.get("title", "Untitled")
    artist = item.get("artist", "Unknown")
    platform = item.get("platform", "?")
    usage = item.get("usage_count", 0)
    score = item.get("trend_score", 0.0)

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown(f"**{title}** by *{artist}*")
        st.caption(f"Platform: `{platform}` · Audio ID: `{item.get('audio_id', '')}`")
    with col2:
        st.metric("Uses", f"{usage:,}")
    with col3:
        st.metric("Trend Score", f"{score:.0%}")


def _render_competitor_watch(api_base: str | None) -> None:
    st.markdown("### Competitor Watchlist")

    from apps.dashboard.data_loader import _load_fixture, _fetch_api

    if api_base is None:
        items = _load_fixture("competitor_watchlist")
    else:
        items = _fetch_api(api_base, "/competitor_watchlist")

    if not items:
        st.info("No competitors tracked yet.")
        return

    for item in items:
        handle = item.get("handle", "?")
        platform = item.get("platform", "?")
        followers = item.get("follower_count", 0)
        engagement = item.get("avg_engagement", 0.0)
        notes = item.get("notes", "")

        st.markdown(
            f"**{handle}** on `{platform}` · "
            f"{followers:,} followers · {engagement:.1f}% avg engagement"
        )
        if notes:
            st.caption(notes)
