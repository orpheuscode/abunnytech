"""
abunnytech Pipeline Dashboard
==============================
Streamlit dashboard for visualizing the full AI-creator pipeline.
Run:  streamlit run apps/dashboard/app.py
"""

from __future__ import annotations

import time

import streamlit as st

st.set_page_config(
    page_title="abunnytech Pipeline",
    page_icon="\U0001f430",
    layout="wide",
    initial_sidebar_state="expanded",
)

from apps.dashboard.data_loader import (  # noqa: E402
    load_content_packages,
    load_distribution_records,
    load_identities,
    load_optimization_directives,
    load_redo_queue,
    load_trending_audio,
    load_video_blueprints,
)
from apps.dashboard.pages import analytics, catalog, content, discovery, distribution, identity  # noqa: E402

PAGES = {
    "\U0001f9ec Identity": "identity",
    "\U0001f50d Discovery": "discovery",
    "\U0001f3ac Content": "content",
    "\U0001f4e6 Distribution": "distribution",
    "\U0001f4ca Analytics": "analytics",
    "\U0001f6cd\ufe0f Monetization": "catalog",
    "\U0001f3ae Demo Control": "demo",
    "\U0001f3ac Guided Demo": "guided",
}

PIPELINE_STAGES = [
    ("Stage 0", "Identity", "#6c5ce7", "Define the AI persona"),
    ("Stage 1", "Discovery", "#00b894", "Discover trends & competitors"),
    ("Stage 2", "Content", "#fdcb6e", "Generate video blueprints & packages"),
    ("Stage 3", "Distribution", "#0984e3", "Distribute to platforms"),
    ("Stage 4", "Analytics", "#e17055", "Measure & optimize"),
    ("Stage 5", "Monetization", "#a29bfe", "Products & brand deals"),
]


def main() -> None:
    _inject_global_css()

    with st.sidebar:
        _render_sidebar()

    page = st.session_state.get("current_page", "identity")
    api_base = st.session_state.get("api_base")

    if page == "identity":
        _page_header("Stage 0: Identity Matrix", "#6c5ce7")
        identity.render(api_base)
    elif page == "discovery":
        _page_header("Stage 1: Discovery Queue", "#00b894")
        discovery.render(api_base)
    elif page == "content":
        _page_header("Stage 2: Content Generation", "#fdcb6e")
        content.render(api_base)
    elif page == "distribution":
        _page_header("Stage 3: Distribution", "#0984e3")
        distribution.render(api_base)
    elif page == "analytics":
        _page_header("Stage 4: Analytics & Directives", "#e17055")
        analytics.render(api_base)
    elif page == "catalog":
        _page_header("Stage 5: Monetization", "#a29bfe")
        catalog.render(api_base)
    elif page == "demo":
        _page_header("Demo Control Surface", "#2d3436")
        _render_demo_control(api_base)
    elif page == "guided":
        _render_guided_demo(api_base)


def _render_sidebar() -> None:
    st.markdown(
        """
        <div style="text-align:center; margin-bottom:1rem;">
            <h1 style="margin:0; font-size:1.6rem;">\U0001f430 abunnytech</h1>
            <p style="margin:0; color:#636e72; font-size:0.85rem;">
                AI Creator Pipeline Dashboard
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("##### Pipeline Stages")

    for label, key in PAGES.items():
        if st.button(label, key=f"nav_{key}", use_container_width=True):
            st.session_state["current_page"] = key

    st.markdown("---")
    st.markdown("##### Data Source")

    source = st.radio(
        "Load data from",
        ["Fixture JSON (demo)", "Local API"],
        index=0,
        key="data_source_radio",
    )

    if source == "Local API":
        api_url = st.text_input(
            "API Base URL",
            value="http://localhost:8000",
            key="api_url_input",
        )
        st.session_state["api_base"] = api_url
    else:
        st.session_state["api_base"] = None

    st.markdown("---")
    st.markdown(
        '<p style="color:#b2bec3; font-size:0.75rem; text-align:center;">'
        "DiamondHacks 2026 &bull; abunnytech</p>",
        unsafe_allow_html=True,
    )


def _page_header(title: str, color: str) -> None:
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, {color} 0%, {color}88 100%);
                    padding: 1.25rem 1.5rem; border-radius: 12px; margin-bottom: 1.5rem;
                    color: white;">
            <h1 style="margin:0; font-size:1.8rem; color:white;">{title}</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Demo Control Surface
# ---------------------------------------------------------------------------

def _render_demo_control(api_base: str | None) -> None:
    st.markdown("Operator tools for running demos, inspecting artifacts, and monitoring the pipeline.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Dry-Run Demo")
        st.markdown(
            "Simulate a full pipeline pass from identity creation through "
            "distribution without posting to any real platform."
        )
        if st.button("Run Dry-Run Demo", type="primary", key="dry_run_btn"):
            _run_dry_run_demo(api_base)

    with col2:
        st.markdown("### Pipeline Status")
        _render_pipeline_health(api_base)

    st.markdown("---")

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("### Inspect Artifacts")
        _render_artifact_inspector(api_base)

    with col4:
        st.markdown("### Latest Directive / Redo Queue")
        _render_directive_summary(api_base)


def _run_dry_run_demo(api_base: str | None) -> None:
    stages = [
        ("Loading identity...", "TechBunny identity loaded"),
        ("Scanning trends...", "3 trending audio items discovered"),
        ("Analyzing competitors...", "2 competitor profiles analyzed"),
        ("Generating blueprint...", "Video blueprint created: 5 scenes, 30s"),
        ("Rendering content...", "Content package assembled (8.4 MB)"),
        ("Distributing (dry run)...", "Dry-run posted to TikTok + Instagram"),
        ("Collecting metrics...", "Performance metrics snapshot taken"),
        ("Generating directives...", "1 optimization envelope, 3 actions"),
    ]

    progress = st.progress(0)
    status = st.empty()

    for i, (msg, result) in enumerate(stages):
        status.info(msg)
        time.sleep(0.6)
        progress.progress((i + 1) / len(stages))
        status.success(result)
        time.sleep(0.3)

    st.balloons()
    st.success("Dry-run complete! All pipeline stages executed successfully in demo mode.")


def _render_pipeline_health(api_base: str | None) -> None:
    identities = load_identities(api_base)
    trending = load_trending_audio(api_base)
    blueprints = load_video_blueprints(api_base)
    packages = load_content_packages(api_base)
    records = load_distribution_records(api_base)

    checks = [
        ("Identities", len(identities)),
        ("Trending Audio", len(trending)),
        ("Blueprints", len(blueprints)),
        ("Content Packages", len(packages)),
        ("Distribution Records", len(records)),
    ]

    for label, count in checks:
        icon = "\u2705" if count > 0 else "\u26a0\ufe0f"
        st.markdown(f"{icon} **{label}:** {count} record(s)")


def _render_artifact_inspector(api_base: str | None) -> None:
    artifact_type = st.selectbox(
        "Select artifact type",
        [
            "Identity Matrix",
            "Video Blueprint",
            "Content Package",
            "Distribution Record",
            "Optimization Directive",
        ],
        key="artifact_type_select",
    )

    loaders = {
        "Identity Matrix": load_identities,
        "Video Blueprint": load_video_blueprints,
        "Content Package": load_content_packages,
        "Distribution Record": load_distribution_records,
        "Optimization Directive": load_optimization_directives,
    }

    loader = loaders.get(artifact_type)
    if loader is None:
        return

    data = loader(api_base)
    if not data:
        st.info(f"No {artifact_type} artifacts found.")
        return

    if isinstance(data, list):
        labels = [
            f"{d.get('name', d.get('title', str(d.get('id', ''))[:8]))}"
            for d in data
        ]
        idx = st.selectbox("Select record", range(len(labels)), format_func=lambda i: labels[i], key="artifact_record_select")
        selected = data[idx]
    else:
        selected = data

    st.json(selected)


def _render_directive_summary(api_base: str | None) -> None:
    directives = load_optimization_directives(api_base)
    redo = load_redo_queue(api_base)

    if directives:
        latest = directives[0]
        st.markdown(f"**Latest directive:** {latest.get('summary', 'n/a')[:120]}...")
        st.markdown(f"**Confidence:** {latest.get('confidence', 0):.0%}")
        st.markdown(f"**Actions:** {len(latest.get('directives', []))}")
    else:
        st.info("No directives yet.")

    st.markdown("---")
    if redo:
        pending = [r for r in redo if not r.get("processed")]
        st.markdown(f"**Redo queue:** {len(pending)} pending item(s)")
        for item in pending:
            st.markdown(
                f"- **{item.get('reason', '').replace('_', ' ').title()}** "
                f"&rarr; Stage {item.get('target_stage', '?')}, "
                f"P{item.get('priority', '?')}"
            )
    else:
        st.success("Redo queue is empty.")


# ---------------------------------------------------------------------------
# Guided Demo
# ---------------------------------------------------------------------------

def _render_guided_demo(api_base: str | None) -> None:
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #2d3436 0%, #636e72 100%);
                    padding: 1.5rem; border-radius: 12px; margin-bottom: 1.5rem; color: white;">
            <h1 style="margin:0; color:white;">\U0001f3ac Guided Pipeline Demo</h1>
            <p style="margin:0.5rem 0 0 0; opacity:0.9;">
                Walk through each stage of the abunnytech AI creator pipeline.
                Use the controls below to step through the story.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "demo_step" not in st.session_state:
        st.session_state["demo_step"] = 0

    steps = [
        _demo_step_overview,
        _demo_step_identity,
        _demo_step_discovery,
        _demo_step_content,
        _demo_step_distribution,
        _demo_step_analytics,
        _demo_step_monetization,
        _demo_step_finale,
    ]

    step = st.session_state["demo_step"]
    total = len(steps)

    st.progress((step + 1) / total)
    st.markdown(f"**Step {step + 1} of {total}**")

    steps[step](api_base)

    st.markdown("---")
    nav_cols = st.columns(3)
    with nav_cols[0]:
        if step > 0 and st.button("\u2190 Previous", key="prev_step"):
            st.session_state["demo_step"] = step - 1
            st.rerun()
    with nav_cols[1]:
        st.markdown(f"<p style='text-align:center; color:#636e72;'>{step + 1}/{total}</p>", unsafe_allow_html=True)
    with nav_cols[2]:
        if step < total - 1 and st.button("Next \u2192", key="next_step", type="primary"):
            st.session_state["demo_step"] = step + 1
            st.rerun()


def _demo_step_overview(api_base: str | None) -> None:
    st.markdown("## The Pipeline Story")
    st.markdown(
        "**abunnytech** is an autonomous AI-creator pipeline that takes a persona from "
        "concept to content to distribution to analytics -- and loops back to improve."
    )

    st.markdown("### Pipeline Architecture")
    for stage_num, name, color, desc in PIPELINE_STAGES:
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; margin-bottom:0.5rem;">
                <div style="background:{color}; color:white; padding:4px 12px;
                            border-radius:8px; min-width:80px; text-align:center;
                            font-weight:bold; margin-right:1rem;">{stage_num}</div>
                <div>
                    <strong>{name}</strong>
                    <span style="color:#636e72; margin-left:0.5rem;">{desc}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        "\n> The feedback loop from Stage 4 back to Stages 1-3 is what makes this "
        "pipeline autonomous and self-improving."
    )


def _demo_step_identity(api_base: str | None) -> None:
    st.markdown("## Stage 0: Identity Matrix")
    st.markdown(
        "Every pipeline run starts with an **Identity Matrix** -- the persona definition "
        "that feeds all downstream stages. This is who our AI creator *is*."
    )
    identity.render(api_base)


def _demo_step_discovery(api_base: str | None) -> None:
    st.markdown("## Stage 1: Discovery Queue")
    st.markdown(
        "The pipeline scans platforms for **trending audio**, analyzes **competitors**, "
        "and builds a **training manifest** to inform content generation."
    )
    discovery.render(api_base)


def _demo_step_content(api_base: str | None) -> None:
    st.markdown("## Stage 2: Content Generation")
    st.markdown(
        "Using discovery insights and the identity matrix, the pipeline generates "
        "**video blueprints** with scene-by-scene scripts, then assembles "
        "**content packages** with rendered assets."
    )
    content.render(api_base)


def _demo_step_distribution(api_base: str | None) -> None:
    st.markdown("## Stage 3: Distribution")
    st.markdown(
        "Content packages are queued for distribution. The system supports **dry-run** "
        "mode (no real posting) and **live** posting with engagement tracking."
    )
    distribution.render(api_base)


def _demo_step_analytics(api_base: str | None) -> None:
    st.markdown("## Stage 4: Analytics & Directives")
    st.markdown(
        "Performance metrics feed back into **optimization directives** that target "
        "specific stages. Underperforming content enters the **redo queue** for re-processing."
    )
    analytics.render(api_base)


def _demo_step_monetization(api_base: str | None) -> None:
    st.markdown("## Stage 5: Monetization (Feature-Flagged)")
    st.markdown(
        "When enabled, the pipeline manages a **product catalog** and "
        "**brand outreach** for the AI creator."
    )
    catalog.render(api_base)


def _demo_step_finale(api_base: str | None) -> None:
    st.markdown("## The Full Loop")
    st.markdown(
        "The optimization directive from Stage 4 has already created a redo queue item "
        "targeting Stage 2 -- the pipeline will re-render the second video with a "
        "better hook style. **This is the autonomous feedback loop in action.**"
    )

    st.markdown("### What just happened")
    timeline = [
        ("\U0001f9ec", "Identity created", "TechBunny persona defined with voice, avatar, and content guidelines"),
        ("\U0001f50d", "Trends scanned", "3 trending audio items found, 2 competitors analyzed"),
        ("\U0001f3ac", "Content generated", "2 video blueprints scripted, 1 content package rendered"),
        ("\U0001f4e6", "Distributed", "Dry-run to TikTok + Instagram, 1 live post with 12.4K views"),
        ("\U0001f4ca", "Analyzed", "14.8% engagement rate, 3 optimization directives generated"),
        ("\U0001f504", "Feedback loop", "1 redo queue item: re-render video #2 with better hook"),
    ]

    for emoji, title, desc in timeline:
        st.markdown(
            f"""
            <div style="display:flex; align-items:flex-start; margin-bottom:0.75rem;">
                <span style="font-size:1.5rem; margin-right:0.75rem;">{emoji}</span>
                <div>
                    <strong>{title}</strong><br/>
                    <span style="color:#636e72;">{desc}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.balloons()
    st.success("Demo complete! The autonomous AI-creator pipeline is ready for prime time.")


# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------

def _inject_global_css() -> None:
    st.markdown(
        """
        <style>
        /* Clean up Streamlit defaults */
        .block-container { padding-top: 1rem; }
        [data-testid="stSidebar"] { background: #f8f9fa; }
        [data-testid="stSidebar"] .stButton > button {
            text-align: left;
            border: none;
            background: transparent;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            transition: background 0.15s;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background: #dfe6e9;
        }
        .stMetric {
            background: #f8f9fa;
            padding: 0.75rem;
            border-radius: 10px;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 0.5rem 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
