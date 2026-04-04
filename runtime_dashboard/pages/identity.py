"""Stage 0 – Identity Matrix page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from runtime_dashboard.data_loader import load_identities


def render(api_base: str | None) -> None:
    identities = load_identities(api_base)

    if not identities:
        st.info("No identities found. Seed data or connect to the API.")
        return

    st.markdown(f"**{len(identities)}** identity profile(s) loaded.")

    for ident in identities:
        _render_identity_card(ident)


def _render_identity_card(ident: dict[str, Any]) -> None:
    name = ident.get("name", "Unnamed")
    archetype = ident.get("archetype", "unknown")
    tagline = ident.get("tagline", "")
    platforms = ident.get("platforms", [])
    voice = ident.get("voice", {})
    avatar = ident.get("avatar", {})

    platform_badges = "  ".join(
        f"`{p.get('platform', '?')}` **{p.get('handle', '')}**" for p in platforms
    )

    st.markdown(
        f"""
        <div style="background:#f8f9fa; border-radius:12px; padding:1.25rem;
                    margin-bottom:1rem; border-left:4px solid #6c5ce7;">
            <h3 style="margin:0 0 0.25rem 0;">{name}</h3>
            <p style="margin:0; color:#636e72; font-style:italic;">{tagline}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(3)

    with cols[0]:
        st.markdown("**Archetype**")
        st.code(archetype)

    with cols[1]:
        st.markdown("**Platforms**")
        if platform_badges:
            st.markdown(platform_badges)
        else:
            st.caption("None configured")

    with cols[2]:
        st.markdown("**Voice**")
        st.caption(
            f"Provider: {voice.get('provider', 'n/a')} · "
            f"Style: {voice.get('style', 'n/a')} · "
            f"Speed: {voice.get('speed', 1.0)}"
        )

    if avatar.get("avatar_url"):
        st.caption(f"Avatar style: {avatar.get('style', 'n/a')} · BG: {avatar.get('background_color', '#000')}")

    st.markdown("---")
