from __future__ import annotations

import os

import httpx
import streamlit as st

API_BASE = os.environ.get("PIPELINE_API_BASE", "http://127.0.0.1:8000")


def main() -> None:
    st.set_page_config(page_title="Creator Pipeline — Stages 0–2", layout="wide")
    st.title("Autonomous creator pipeline (demo)")
    st.caption("Stages 0–2: identity, discover/analyze, generate. Sandbox / disclosure-aware defaults.")

    if "run_id" not in st.session_state:
        st.session_state.run_id = ""

    with st.sidebar:
        st.subheader("API")
        base = st.text_input("API base URL", value=API_BASE)
        st.session_state.api_base = base.rstrip("/")
        r = httpx.get(f"{st.session_state.api_base}/settings", timeout=10.0)
        if r.is_success:
            st.json(r.json())
        else:
            st.warning("API not reachable — start the FastAPI server.")
        st.divider()
        st.subheader("Stage 5")
        st.caption("Monetization is feature-flagged off in settings for the main demo.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Stage 0 — Identity")
        name = st.text_input("Display name", value="Demo Creator")
        niche = st.text_input("Niche", value="indie hacking")
        tone = st.text_input("Tone", value="playful")
        topics = st.text_input("Topics (comma-separated)", value="AI, startups, demos")

        if st.button("Create run"):
            cr = httpx.post(f"{st.session_state.api_base}/runs", timeout=30.0)
            cr.raise_for_status()
            st.session_state.run_id = cr.json()["run_id"]
            st.success(f"run_id = {st.session_state.run_id}")

        if st.button("Run stage 0") and st.session_state.run_id:
            payload = {
                "display_name": name,
                "niche": niche,
                "tone": tone,
                "topics": [t.strip() for t in topics.split(",") if t.strip()],
            }
            u = f"{st.session_state.api_base}/runs/{st.session_state.run_id}/stage0"
            rr = httpx.post(u, json=payload, timeout=60.0)
            if rr.is_success:
                st.session_state.stage0 = rr.json()
                st.success("Stage 0 complete")
            else:
                st.error(rr.text)

        if st.session_state.get("stage0"):
            st.json(st.session_state.stage0.get("identity_matrix", {}))

    with col2:
        st.subheader("Stage 1 — Discover")
        if st.button("Run stage 1") and st.session_state.run_id:
            u = f"{st.session_state.api_base}/runs/{st.session_state.run_id}/stage1"
            rr = httpx.post(u, timeout=60.0)
            if rr.is_success:
                st.session_state.stage1 = rr.json()
                st.success("Stage 1 complete")
            else:
                st.error(rr.text)
        if st.session_state.get("stage1"):
            st.json(st.session_state.stage1.get("video_blueprint", {}))

    st.subheader("Stage 2 — Generate")
    if st.button("Run stage 2") and st.session_state.run_id:
        u = f"{st.session_state.api_base}/runs/{st.session_state.run_id}/stage2"
        rr = httpx.post(u, timeout=120.0)
        if rr.is_success:
            st.session_state.stage2 = rr.json()
            st.success("Stage 2 complete")
        else:
            st.error(rr.text)
    if st.session_state.get("stage2"):
        cp = st.session_state.stage2.get("content_package", {})
        st.json(cp)
        path = cp.get("primary_video", {}).get("path")
        if path:
            st.code(path, language="text")

    st.subheader("Artifacts (SQLite mirror)")
    if st.button("Refresh artifacts") and st.session_state.run_id:
        u = f"{st.session_state.api_base}/runs/{st.session_state.run_id}/artifacts"
        ar = httpx.get(u, timeout=30.0)
        if ar.is_success:
            st.session_state.artifacts = ar.json()
        else:
            st.session_state.artifacts = {}
            st.warning(ar.text)
    if st.session_state.get("artifacts"):
        st.json(st.session_state.artifacts)


main()
