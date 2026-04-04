"""
Small Streamlit UI to exercise the Creator Pipeline API (stages 0–2).

Run from repo root (requires streamlit + httpx, e.g. pipeline-dashboard workspace package):

  uv run --project apps/m1/dashboard streamlit run integration/debug_dashboard.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_path = _ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()

DEFAULT_BASE = os.environ.get("PIPELINE_API_BASE", "http://127.0.0.1:8000")


def _log(session: dict[str, Any], method: str, url: str, status: int, ms: float) -> None:
    session.setdefault("req_log", []).append(
        {"method": method, "url": url, "status": status, "ms": round(ms, 2)}
    )
    session["req_log"] = session["req_log"][-30:]


def main() -> None:
    st.set_page_config(page_title="Pipeline debug", layout="wide")
    st.title("Pipeline API — debug dashboard")
    st.caption("Health checks, stage runs, and artifact inspection (handles list-typed artifacts).")

    if "run_id" not in st.session_state:
        st.session_state.run_id = ""
    if "req_log" not in st.session_state:
        st.session_state.req_log = []

    with st.sidebar:
        st.subheader("Connection")
        base = st.text_input("API base URL", value=DEFAULT_BASE)
        api_base = base.rstrip("/")
        st.caption("Set `PIPELINE_API_BASE` in `.env` or here.")

        t0 = time.perf_counter()
        try:
            hr = httpx.get(f"{api_base}/health", timeout=10.0)
            ms = (time.perf_counter() - t0) * 1000
            _log(st.session_state, "GET", f"{api_base}/health", hr.status_code, ms)
            st.success("health: ok") if hr.is_success else st.error(f"health: {hr.status_code}")
        except httpx.HTTPError as e:
            st.error(f"health failed: {e}")
            hr = None

        t0 = time.perf_counter()
        try:
            sr = httpx.get(f"{api_base}/settings", timeout=10.0)
            ms = (time.perf_counter() - t0) * 1000
            _log(st.session_state, "GET", f"{api_base}/settings", sr.status_code, ms)
            if sr.is_success:
                st.json(sr.json())
            else:
                st.warning(f"settings: {sr.status_code}")
        except httpx.HTTPError as e:
            st.warning(f"settings: {e}")

    tab_run, tab_art, tab_log, tab_curl = st.tabs(
        ["Run stages", "Artifacts", "Request log", "cURL snippets"]
    )

    with tab_run:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("POST /runs"):
                t0 = time.perf_counter()
                cr = httpx.post(f"{api_base}/runs", timeout=30.0)
                ms = (time.perf_counter() - t0) * 1000
                _log(st.session_state, "POST", f"{api_base}/runs", cr.status_code, ms)
                if cr.is_success:
                    st.session_state.run_id = cr.json()["run_id"]
                    st.success(f"run_id = {st.session_state.run_id}")
                else:
                    st.error(cr.text)

        with c2:
            pasted = st.text_input("Paste run_id", placeholder="uuid from API or DB")
            if st.button("Use pasted run_id") and pasted.strip():
                st.session_state.run_id = pasted.strip()
                st.rerun()

        rid = st.session_state.run_id.strip()
        st.markdown(f"**Active run_id:** `{rid or '—'}`")
        st.divider()
        name = st.text_input("Stage 0 display_name", value="Debug Creator")
        niche = st.text_input("Stage 0 niche", value="pipeline testing")
        tone = st.text_input("Stage 0 tone", value="dry")
        topics = st.text_input("Stage 0 topics (comma-separated)", value="debug, api")

        b0, b1, b2 = st.columns(3)
        with b0:
            go0 = st.button("Run stage 0", disabled=not rid)
        with b1:
            go1 = st.button("Run stage 1", disabled=not rid)
        with b2:
            go2 = st.button("Run stage 2", disabled=not rid)

        if go0 and rid:
            payload = {
                "display_name": name,
                "niche": niche,
                "tone": tone,
                "topics": [t.strip() for t in topics.split(",") if t.strip()],
            }
            u = f"{api_base}/runs/{rid}/stage0"
            t0 = time.perf_counter()
            rr = httpx.post(u, json=payload, timeout=120.0)
            ms = (time.perf_counter() - t0) * 1000
            _log(st.session_state, "POST", u, rr.status_code, ms)
            st.session_state.last_stage0 = rr.json() if rr.is_success else {"error": rr.text}
            st.session_state.last_status_0 = rr.status_code

        if go1 and rid:
            u = f"{api_base}/runs/{rid}/stage1"
            t0 = time.perf_counter()
            rr = httpx.post(u, timeout=120.0)
            ms = (time.perf_counter() - t0) * 1000
            _log(st.session_state, "POST", u, rr.status_code, ms)
            st.session_state.last_stage1 = rr.json() if rr.is_success else {"error": rr.text}
            st.session_state.last_status_1 = rr.status_code

        if go2 and rid:
            u = f"{api_base}/runs/{rid}/stage2"
            t0 = time.perf_counter()
            rr = httpx.post(u, timeout=180.0)
            ms = (time.perf_counter() - t0) * 1000
            _log(st.session_state, "POST", u, rr.status_code, ms)
            st.session_state.last_stage2 = rr.json() if rr.is_success else {"error": rr.text}
            st.session_state.last_status_2 = rr.status_code

        for label, key, sk in (
            ("Stage 0", "last_stage0", "last_status_0"),
            ("Stage 1", "last_stage1", "last_status_1"),
            ("Stage 2", "last_stage2", "last_status_2"),
        ):
            if key in st.session_state:
                st.subheader(label)
                if sk in st.session_state:
                    st.caption(f"HTTP {st.session_state[sk]}")
                st.json(st.session_state[key])

    with tab_art:
        rid = st.session_state.run_id.strip()
        if st.button("GET /artifacts", disabled=not rid):
            u = f"{api_base}/runs/{rid}/artifacts"
            t0 = time.perf_counter()
            ar = httpx.get(u, timeout=60.0)
            ms = (time.perf_counter() - t0) * 1000
            _log(st.session_state, "GET", u, ar.status_code, ms)
            st.session_state.artifacts_raw = ar.json() if ar.is_success else {"error": ar.text}
            st.session_state.artifacts_status = ar.status_code
        if "artifacts_raw" in st.session_state:
            st.caption(f"HTTP {st.session_state.get('artifacts_status', '')}")
            data = st.session_state.artifacts_raw
            if isinstance(data, dict) and "error" not in data:
                for k in sorted(data.keys()):
                    st.markdown(f"**{k}**")
                    st.json(data[k])
            else:
                st.json(data)

    with tab_log:
        st.dataframe(st.session_state.req_log, use_container_width=True)

    with tab_curl:
        rid = st.session_state.run_id.strip() or "<run_id>"
        st.code(
            "\n".join(
                [
                    f'export PIPELINE_API_BASE="{api_base}"',
                    'curl -s "$PIPELINE_API_BASE/health"',
                    'curl -s "$PIPELINE_API_BASE/settings"',
                    'curl -s -X POST "$PIPELINE_API_BASE/runs"',
                    "curl -s -X POST "
                    f'"$PIPELINE_API_BASE/runs/{rid}/stage0" '
                    r'-H "Content-Type: application/json" '
                    r"-d "
                    '\'{"display_name":"T","niche":"n","tone":"playful","topics":[]}\'',
                    f'curl -s -X POST "$PIPELINE_API_BASE/runs/{rid}/stage1"',
                    f'curl -s -X POST "$PIPELINE_API_BASE/runs/{rid}/stage2"',
                    f'curl -s "$PIPELINE_API_BASE/runs/{rid}/artifacts"',
                ]
            ),
            language="bash",
        )


if __name__ == "__main__":
    main()
