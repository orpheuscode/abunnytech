"""Streamlit dashboard for the abunnytech autonomous AI creator pipeline.

Run: streamlit run services/dashboard/app.py
"""

from __future__ import annotations

import httpx
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="abunnytech - AI Creator Pipeline",
    page_icon="🐰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# High-contrast dark theme CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ---- Global ---- */
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: #0f0f1a !important;
    color: #e2e8f0 !important;
}

/* Sidebar — deep indigo, distinct from main area */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #16132d 0%, #1e1b3a 100%) !important;
    border-right: 2px solid #7c3aed !important;
}
[data-testid="stSidebar"] > div:first-child {
    background: transparent !important;
}
[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #c4b5fd !important;
}

/* ---- Buttons ---- */
.stButton > button,
button[kind="primary"],
button[kind="secondary"],
[data-testid="stFormSubmitButton"] > button {
    background-color: #a855f7 !important;
    color: #ffffff !important;
    border: 2px solid #c084fc !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.5rem 1.25rem !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover,
button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button:hover {
    background-color: #9333ea !important;
    border-color: #e9d5ff !important;
    box-shadow: 0 0 12px rgba(168, 85, 247, 0.5) !important;
}
.stButton > button:active {
    background-color: #7e22ce !important;
}

/* ---- Inputs, selects, text areas ---- */
input, textarea,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
.stSelectbox > div > div,
.stMultiSelect > div > div,
[data-baseweb="select"] > div,
[data-baseweb="input"] > div {
    background-color: #1e1e36 !important;
    color: #e2e8f0 !important;
    border: 1.5px solid #6d28d9 !important;
    border-radius: 6px !important;
}
input:focus, textarea:focus,
[data-testid="stTextInput"] input:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.35) !important;
}

/* Dropdown menus */
[data-baseweb="popover"],
[data-baseweb="menu"],
ul[role="listbox"] {
    background-color: #1e1e36 !important;
    border: 1px solid #6d28d9 !important;
}
[data-baseweb="menu"] li,
ul[role="listbox"] li {
    color: #e2e8f0 !important;
}
[data-baseweb="menu"] li:hover,
ul[role="listbox"] li:hover {
    background-color: #2d2b55 !important;
}

/* ---- Tabs ---- */
.stTabs [data-baseweb="tab-list"] {
    background-color: #1a1a2e !important;
    border-radius: 8px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    color: #94a3b8 !important;
    background-color: transparent !important;
    border-radius: 6px !important;
    padding: 0.5rem 1rem !important;
    font-weight: 500 !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #ffffff !important;
    background-color: #a855f7 !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #e2e8f0 !important;
    background-color: #2d2b55 !important;
}

/* ---- Expanders ---- */
[data-testid="stExpander"] {
    background-color: #1a1a2e !important;
    border: 1px solid #374151 !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
    color: #e2e8f0 !important;
}

/* ---- Metrics ---- */
[data-testid="stMetric"] {
    background-color: #1a1a2e !important;
    border: 1px solid #374151 !important;
    border-radius: 10px !important;
    padding: 1rem !important;
}
[data-testid="stMetricLabel"] {
    color: #94a3b8 !important;
}
[data-testid="stMetricValue"] {
    color: #a855f7 !important;
    font-weight: 700 !important;
}

/* ---- Info / Success / Error boxes ---- */
[data-testid="stAlert"] {
    border-radius: 8px !important;
}

/* ---- Tables ---- */
table {
    background-color: #1a1a2e !important;
    color: #e2e8f0 !important;
}
th {
    background-color: #2d2b55 !important;
    color: #c084fc !important;
    font-weight: 600 !important;
}
td {
    border-color: #374151 !important;
}

/* ---- Checkbox ---- */
[data-testid="stCheckbox"] label span {
    color: #e2e8f0 !important;
}

/* ---- Radio buttons in sidebar ---- */
[data-testid="stSidebar"] [role="radiogroup"] label {
    background-color: #1e1b3a !important;
    border: 1px solid #4c1d95 !important;
    border-radius: 8px !important;
    padding: 0.45rem 0.85rem !important;
    margin-bottom: 4px !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    border-color: #a855f7 !important;
    background-color: #2d2b55 !important;
    box-shadow: 0 0 8px rgba(124, 58, 237, 0.3) !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"],
[data-testid="stSidebar"] [role="radiogroup"] div[aria-checked="true"] + label {
    background-color: #7c3aed !important;
    border-color: #a78bfa !important;
    color: #ffffff !important;
}

/* ---- JSON viewer ---- */
[data-testid="stJson"] {
    background-color: #1e1e36 !important;
    border: 1px solid #374151 !important;
    border-radius: 6px !important;
}

/* ---- Form container ---- */
[data-testid="stForm"] {
    background-color: #1a1a2e !important;
    border: 1px solid #374151 !important;
    border-radius: 10px !important;
    padding: 1.5rem !important;
}

/* ---- Spinner ---- */
.stSpinner > div {
    border-top-color: #a855f7 !important;
}

/* ---- Links ---- */
a {
    color: #c084fc !important;
}
a:hover {
    color: #e9d5ff !important;
}

/* ---- Scrollbar ---- */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: #0f0f1a;
}
::-webkit-scrollbar-thumb {
    background: #6d28d9;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #a855f7;
}
</style>
""", unsafe_allow_html=True)


def api_get(path: str) -> dict | list | None:
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post(path: str, json: dict | None = None) -> dict | list | None:
    try:
        r = httpx.post(f"{API_BASE}{path}", json=json or {}, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


# --- Sidebar ---
st.sidebar.title("🐰 abunnytech")
st.sidebar.caption("Autonomous AI Creator Pipeline")

health = api_get("/health")
if health:
    dry_run = health.get("dry_run", True)
    st.sidebar.metric("Mode", "🔒 Dry Run" if dry_run else "🟢 Live")
    st.sidebar.metric("Stage 5", "On" if health.get("stage5_monetize") else "Off")

page = st.sidebar.radio(
    "Navigate",
    [
        "🏠 Overview",
        "🎭 Identity (Stage 0)",
        "🔍 Discover (Stage 1)",
        "🎬 Generate (Stage 2)",
        "📡 Distribute (Stage 3)",
        "📊 Analyze (Stage 4)",
        "🚀 Demo Pipeline",
    ],
)


# --- Pages ---

if page == "🏠 Overview":
    st.title("Autonomous AI Creator Pipeline")
    st.markdown("")

    stages_data = [
        ("0", "Identity", "Avatar + voice pack creation", "#a855f7"),
        ("1", "Discover", "Viral trend discovery & competitor analysis", "#6366f1"),
        ("2", "Generate", "Video blueprint creation & rendering", "#06b6d4"),
        ("3", "Distribute", "Platform posting & comment engagement", "#10b981"),
        ("4", "Analyze", "Performance metrics & optimization", "#f59e0b"),
        ("5", "Monetize", "Product catalog & brand outreach (feature-flagged)", "#ef4444"),
    ]
    for stage_num, name, desc, color in stages_data:
        st.markdown(
            f'<div style="background:#1a1a2e;border-left:4px solid {color};'
            f'padding:0.75rem 1rem;margin-bottom:0.5rem;border-radius:6px;">'
            f'<span style="color:{color};font-weight:700;font-size:1.1rem;">'
            f'Stage {stage_num}</span>'
            f' &nbsp; <span style="color:#e2e8f0;font-weight:600;">{name}</span>'
            f' &mdash; <span style="color:#94a3b8;">{desc}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    identities = api_get("/identity")
    if identities:
        col1.metric("Identities", len(identities))
    else:
        col1.metric("Identities", 0)

    blueprints = api_get("/generate/blueprints")
    if blueprints:
        col2.metric("Blueprints", len(blueprints))
    else:
        col2.metric("Blueprints", 0)

    records = api_get("/distribute/records")
    if records:
        col3.metric("Distributions", len(records))
    else:
        col3.metric("Distributions", 0)


elif page == "🎭 Identity (Stage 0)":
    st.title("🎭 Stage 0: Identity Matrix")

    tab1, tab2 = st.tabs(["View Identities", "Create Identity"])

    with tab1:
        identities = api_get("/identity")
        if identities:
            for ident in identities:
                with st.expander(f"**{ident['name']}** — {ident['archetype']}", expanded=False):
                    st.json(ident)
        else:
            st.info("No identities yet. Create one or run the demo pipeline.")

    with tab2:
        with st.form("create_identity"):
            col1, col2 = st.columns(2)
            name = col1.text_input("Name", "Avery Bytes")
            archetype = col2.selectbox(
                "Archetype",
                ["educator", "entertainer", "motivator", "reviewer", "storyteller"],
            )
            topics = st.text_input("Topics (comma-separated)", "AI, productivity, creator tools")
            platforms = st.multiselect("Platforms", ["tiktok", "instagram", "youtube"], default=["tiktok"])

            if st.form_submit_button("Create Identity"):
                result = api_post("/identity", {
                    "name": name,
                    "archetype": archetype,
                    "topics": [t.strip() for t in topics.split(",")],
                    "platforms": platforms,
                })
                if result:
                    st.success(f"Created identity: {result.get('name', 'Unknown')}")
                    st.json(result)

        if st.button("Create Default Demo Identity"):
            result = api_post("/identity/default")
            if result:
                st.success(f"Created: {result.get('name', 'Unknown')}")
                st.json(result)


elif page == "🔍 Discover (Stage 1)":
    st.title("🔍 Stage 1: Discover & Analyze")

    tab1, tab2 = st.tabs(["Trending", "Competitors"])

    with tab1:
        identities = api_get("/identity") or []
        identity_options = {f"{i['name']} ({i['id'][:8]})": i["id"] for i in identities}

        if identity_options:
            selected = st.selectbox("Identity", list(identity_options.keys()), key="trend_identity")
            identity_id = identity_options[selected]
            platform = st.selectbox("Platform", ["tiktok", "instagram", "youtube"], key="trend_platform")

            if st.button("Discover Trends"):
                result = api_post("/discover/trending", {
                    "platform": platform,
                    "identity_id": identity_id,
                })
                if result:
                    st.success(f"Found {len(result)} trends")
                    for item in result:
                        st.write(f"🎵 **{item.get('title', 'Unknown')}** — {item.get('usage_count', 0):,} uses")
        else:
            st.info("Create an identity first.")

    with tab2:
        if identity_options:
            selected = st.selectbox("Identity", list(identity_options.keys()), key="comp_identity")
            identity_id = identity_options[selected]
            platform = st.selectbox("Platform", ["tiktok", "instagram", "youtube"], key="comp_platform")
            handles = st.text_input("Handles (comma-separated)", "@creator1, @creator2")

            if st.button("Analyze Competitors"):
                result = api_post("/discover/competitors", {
                    "platform": platform,
                    "handles": [h.strip() for h in handles.split(",")],
                    "identity_id": identity_id,
                })
                if result:
                    st.success(f"Analyzed {len(result)} competitors")
                    for item in result:
                        st.json(item)


elif page == "🎬 Generate (Stage 2)":
    st.title("🎬 Stage 2: Generate Content")

    tab1, tab2, tab3 = st.tabs(["Create Blueprint", "Render", "View"])

    identities = api_get("/identity") or []
    identity_options = {f"{i['name']} ({i['id'][:8]})": i["id"] for i in identities}

    with tab1:
        if identity_options:
            selected = st.selectbox("Identity", list(identity_options.keys()), key="gen_identity")
            identity_id = identity_options[selected]
            title = st.text_input("Video Title", "5 AI Tools You Need in 2025")
            topic = st.text_input("Topic", "AI productivity tools")
            platform = st.selectbox("Platform", ["tiktok", "instagram", "youtube"], key="gen_platform")

            if st.button("Create Blueprint"):
                result = api_post("/generate/blueprint", {
                    "identity_id": identity_id,
                    "title": title,
                    "topic": topic,
                    "platform": platform,
                })
                if result:
                    st.success(f"Blueprint created: {result.get('id', '')[:8]}")
                    st.json(result)
        else:
            st.info("Create an identity first.")

    with tab2:
        blueprints = api_get("/generate/blueprints") or []
        if blueprints:
            bp_options = {f"{b['title']} ({b['id'][:8]})": b["id"] for b in blueprints}
            selected_bp = st.selectbox("Blueprint", list(bp_options.keys()))
            bp_id = bp_options[selected_bp]

            if st.button("Render Content"):
                result = api_post(f"/generate/render/{bp_id}")
                if result:
                    st.success("Content rendered!")
                    st.json(result)
        else:
            st.info("Create a blueprint first.")

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Blueprints")
            blueprints = api_get("/generate/blueprints") or []
            for bp in blueprints:
                with st.expander(f"📋 {bp.get('title', 'Untitled')}", expanded=False):
                    st.json(bp)

        with col2:
            st.subheader("Content Packages")
            packages = api_get("/generate/packages") or []
            for pkg in packages:
                with st.expander(f"📦 {pkg.get('title', 'Untitled')}", expanded=False):
                    st.json(pkg)


elif page == "📡 Distribute (Stage 3)":
    st.title("📡 Stage 3: Distribute & Engage")

    tab1, tab2, tab3 = st.tabs(["Post", "Reply", "Records"])

    with tab1:
        packages = api_get("/generate/packages") or []
        if packages:
            pkg_options = {f"{p['title']} ({p['id'][:8]})": p["id"] for p in packages}
            selected_pkg = st.selectbox("Content Package", list(pkg_options.keys()))
            pkg_id = pkg_options[selected_pkg]
            platform = st.selectbox("Platform", ["tiktok", "instagram", "youtube"], key="dist_platform")
            dry_run = st.checkbox("Dry Run", value=True)

            if st.button("Post Content"):
                result = api_post("/distribute/post", {
                    "content_package_id": pkg_id,
                    "platform": platform,
                    "dry_run": dry_run,
                })
                if result:
                    st.success(f"Distribution: {result.get('status', 'unknown')}")
                    st.json(result)
        else:
            st.info("Generate a content package first.")

    with tab2:
        records = api_get("/distribute/records") or []
        if records:
            rec_options = {f"{r.get('status', '?')} - {r['id'][:8]}": r for r in records}
            selected_rec = st.selectbox("Distribution Record", list(rec_options.keys()))
            rec = rec_options[selected_rec]

            if st.button("Generate Replies"):
                result = api_post("/distribute/reply", {
                    "distribution_record_id": rec["id"],
                    "identity_id": rec.get("identity_id", ""),
                })
                if result:
                    st.success(f"Generated {len(result.get('replies', []))} replies")
                    for reply in result.get("replies", []):
                        st.write(f"💬 {reply}")
        else:
            st.info("Post content first.")

    with tab3:
        records = api_get("/distribute/records") or []
        for rec in records:
            with st.expander(f"📤 {rec.get('status', '?')} — {rec['id'][:8]}", expanded=False):
                st.json(rec)


elif page == "📊 Analyze (Stage 4)":
    st.title("📊 Stage 4: Analyze & Adapt")

    tab1, tab2 = st.tabs(["Collect & Analyze", "Optimizations"])

    identities = api_get("/identity") or []
    identity_options = {f"{i['name']} ({i['id'][:8]})": i["id"] for i in identities}

    with tab1:
        records = api_get("/distribute/records") or []
        if records:
            rec_options = {f"{r.get('status', '?')} - {r['id'][:8]}": r["id"] for r in records}
            selected_rec = st.selectbox("Distribution Record", list(rec_options.keys()))
            rec_id = rec_options[selected_rec]

            if st.button("Collect Metrics"):
                result = api_post(f"/analyze/collect/{rec_id}")
                if result:
                    st.success(f"Collected {len(result)} metrics")
                    for m in result:
                        st.write(f"📈 {m.get('metric_type', '?')}: {m.get('value', 0):,.1f}")
        else:
            st.info("Create distribution records first.")

    with tab2:
        if identity_options:
            selected = st.selectbox("Identity", list(identity_options.keys()), key="opt_identity")
            identity_id = identity_options[selected]

            if st.button("Generate Optimization"):
                result = api_post(f"/analyze/optimize/{identity_id}")
                if result:
                    st.success("Optimization generated!")
                    st.json(result)
        else:
            st.info("Create an identity first.")


elif page == "🚀 Demo Pipeline":
    st.title("🚀 One-Click Demo Pipeline")

    steps = [
        ("1", "Identity", "Create 'Avery Bytes' persona with avatar + voice pack", "#a855f7"),
        ("2", "Discover", "Find trending TikTok content", "#6366f1"),
        ("3", "Generate", "Script and render a video", "#06b6d4"),
        ("4", "Distribute", "Post (dry-run) and generate comment replies", "#10b981"),
        ("5", "Analyze", "Collect metrics and generate optimization directives", "#f59e0b"),
    ]
    for num, name, desc, color in steps:
        st.markdown(
            f'<div style="background:#1a1a2e;border-left:4px solid {color};'
            f'padding:0.6rem 1rem;margin-bottom:0.4rem;border-radius:6px;">'
            f'<span style="color:{color};font-weight:700;">{num}.</span>'
            f' <span style="color:#e2e8f0;font-weight:600;">{name}</span>'
            f' &mdash; <span style="color:#94a3b8;">{desc}</span></div>',
            unsafe_allow_html=True,
        )
    st.markdown("")

    if st.button("🚀 Run Full Demo Pipeline", type="primary", use_container_width=True):
        with st.spinner("Running pipeline..."):
            result = api_post("/pipeline/demo")
            if result and result.get("demo_complete"):
                st.balloons()
                st.success("Demo pipeline complete!")

                stages = result.get("stages", {})

                def _card(title: str, color: str, items: list[tuple[str, str]]) -> str:
                    rows = "".join(
                        f'<div style="margin:0.25rem 0;">'
                        f'<span style="color:#94a3b8;">{k}:</span> '
                        f'<span style="color:#e2e8f0;font-weight:500;">{v}</span></div>'
                        for k, v in items
                    )
                    return (
                        f'<div style="background:#1a1a2e;border:1px solid {color};'
                        f'border-radius:10px;padding:1rem;margin-bottom:0.75rem;">'
                        f'<div style="color:{color};font-weight:700;font-size:1.05rem;'
                        f'margin-bottom:0.5rem;border-bottom:1px solid #374151;'
                        f'padding-bottom:0.4rem;">{title}</div>{rows}</div>'
                    )

                col1, col2 = st.columns(2)
                with col1:
                    s0 = stages.get("stage0_identity", {})
                    st.markdown(_card("Stage 0: Identity", "#a855f7", [
                        ("Name", s0.get("name", "?")),
                        ("Archetype", s0.get("archetype", "?")),
                        ("ID", f'<code>{s0.get("identity_id", "?")[:12]}...</code>'),
                    ]), unsafe_allow_html=True)

                    s1 = stages.get("stage1_discover", {})
                    st.markdown(_card("Stage 1: Discovery", "#6366f1", [
                        ("Trends found", str(s1.get("trending_count", 0))),
                        ("Top trend", s1.get("top_trend", "?")),
                    ]), unsafe_allow_html=True)

                    s2 = stages.get("stage2_generate", {})
                    st.markdown(_card("Stage 2: Content", "#06b6d4", [
                        ("Title", s2.get("title", "?")),
                        ("Scenes", str(s2.get("scene_count", 0))),
                    ]), unsafe_allow_html=True)

                with col2:
                    s3 = stages.get("stage3_distribute", {})
                    st.markdown(_card("Stage 3: Distribution", "#10b981", [
                        ("Status", s3.get("status", "?")),
                        ("Dry run", str(s3.get("dry_run", True))),
                        ("Replies generated", str(s3.get("reply_count", 0))),
                    ]), unsafe_allow_html=True)

                    s4 = stages.get("stage4_analyze", {})
                    confidence = s4.get("confidence", 0)
                    st.markdown(_card("Stage 4: Analysis", "#f59e0b", [
                        ("Metrics collected", str(s4.get("metrics_collected", 0))),
                        ("Optimizations", str(s4.get("optimization_directives", 0))),
                        ("Confidence", f"{confidence:.0%}"),
                    ]), unsafe_allow_html=True)

                st.subheader("Full Result")
                st.json(result)
            elif result:
                st.error("Pipeline did not complete successfully.")
                st.json(result)
