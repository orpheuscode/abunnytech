# abunnytech - Autonomous AI Creator Pipeline

An end-to-end UGC store pipeline that uses Browser Use, TwelveLabs, Gemini, and Veo to discover winning reels and products, generate ad videos, post them, measure performance, and feed the results back into the next cycle.

## UGC Store Pipeline

Simple one-line version:

> Browser Use finds winning reels and products, TwelveLabs turns reels into structured templates, Gemini decides reuse/remake/discard and writes the Veo prompt, Veo makes the video, and Browser Use posts to Instagram and feeds performance back into the next cycle.

Core APIs used by the intended pipeline:

- **Browser Use** - browses Instagram Reels, extracts visible metrics, downloads reels that pass a threshold, browses AliExpress and social platforms for product discovery, posts generated videos to Instagram, and re-checks posts later for performance data.
- **TwelveLabs** - analyzes downloaded reels and extracts structured video understanding such as scenes/actions, hook, audio/music, and style.
- **Gemini API** - acts as the orchestrator across reel discovery, product discovery, video generation, and social feedback loops; decides whether templates should be reused, remade, or discarded; writes the Veo prompt.
- **Veo 3.1** - generates the final ad/reel video from the Gemini-authored prompt plus reference assets.

Implementation entrypoints for this pipeline:

- `packages/hackathon_pipelines/src/hackathon_pipelines/orchestrator.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/gemini_tool_orchestrator.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/pipelines/reel_discovery.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/pipelines/product_discovery.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/pipelines/video_generation.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/pipelines/social_media.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/adapters/live_api.py`

## Architecture

```text
                       +-------------------------+
                       |  Flask owner dashboard  |  :8501
                       +------------+------------+
                                    |
          +-------------------------+-------------------------+
          |                                                   |
  +-------v--------+                                 +-------v--------+
  | State CRUD API |  :8000                          | Control plane  |  :8001
  | (FastAPI)      |                                 | (FastAPI)      |
  +--------+-------+                                 +--------+-------+
           |                                                    |
           |              +-------------------------------------+
           |              |
  +--------v--------------v------+
  |      Pipeline stages          |
  |  0 Identity · 1 Discovery     |  Persona, trends, competitors
  |  2 Content  · 3 Distribution  |  Blueprints, packages, posting
  |  4 Analytics · 5 Monetization |  Metrics, redo queue
  +----------------+--------------+
                   |
           +-------v--------+        +-----------------+
           | SQLite state   |        | browser_runtime |
           +----------------+        +-----------------+
```

Default ports match `scripts/demo.py` and can be overridden with `--api-port`, `--cp-port`, and `--dash-port`.

## Quickstart

```bash
# 1. Install dependencies
uv sync

# 2. Environment (optional for dry-run)
cp .env.example .env

# 3. Start API + control plane + owner dashboard
uv run python -m scripts.demo

# 4. Open the dashboard
#    http://localhost:8501
```

Note: use `uv run python -m scripts.demo` instead of `uv run python scripts/demo.py`. The module form is the working launcher in this repo because it preserves imports for `runtime_dashboard`.

## Owner Dashboard Only

If the backends are already running:

```bash
uv run python -m runtime_dashboard.flask_owner_app
```

Use the sidebar **Data source** to switch between fixture JSON and the **State CRUD API**. The **API keys** page saves Browser Use, Gemini/Google, and Twelve Labs keys to `runtime_dashboard/.owner_secrets.json` (gitignored); `scripts/demo.py` injects those values into child processes.

## One-Command Demo

```bash
uv run python -m scripts.demo
```

This starts:

| Service | URL | Role |
|--------|-----|------|
| State CRUD API | `http://localhost:8000` | Demo seed data, contract collections |
| Control plane | `http://localhost:8001` | Stage routers, `POST /pipeline/demo` |
| Owner dashboard | `http://localhost:8501` | Pipeline views, API keys, demo controls |

Trigger the pipeline from **Demo Control** in the UI, or:

```bash
curl -X POST http://localhost:8001/pipeline/demo
```

Important: `POST /pipeline/demo` runs the stage-based control-plane demo (`identity -> discover -> generate -> distribute -> analyze`). The more specific Browser Use + TwelveLabs + Gemini + Veo UGC store flow lives in `packages/hackathon_pipelines` and is currently a separate implementation slice.

Options:

- `--no-dashboard` - API + control plane only
- `--seed-only` - seed database and exit
- `--api-port`, `--cp-port`, `--dash-port` - custom ports

## CLI Pipeline Demo

In-process dry-run demo with no HTTP servers:

```bash
uv run python -m orchestrator.cli demo
```

Other commands: `identity`, `status` - see `uv run python -m orchestrator.cli --help`.

## Hackathon Pipeline Smoke

The Browser Use + TwelveLabs + Gemini + Veo implementation is covered by the `hackathon_pipelines` package tests:

```bash
uv run pytest packages/hackathon_pipelines/tests -q
```

These dry-run tests exercise:

- reel discovery -> template creation
- product discovery -> video generation
- publish -> analytics feedback -> template performance update

## Tests and Smoke Checks

```bash
# Full integration test tree
uv run pytest tests -q

# Broader integration smoke
uv run python scripts/smoke.py --verbose
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` | No real platform posts when true |
| `FEATURE_STAGE5_MONETIZE` | `false` | Enable Stage 5 monetization endpoints and data |
| `DATABASE_URL` | `sqlite+aiosqlite:///./abunnytech.db` | Async SQLAlchemy database URL |
| `DASHBOARD_PORT` | `8501` | Owner dashboard listen port |
| `OWNER_DASHBOARD_SECRET` | _(dev default)_ | Flask session secret |
| `CONTROL_PLANE_HOST` / `CONTROL_PLANE_PORT` | `0.0.0.0` / `8000` | `scripts/demo.py` uses `8001` for the control plane unless overridden |
| `OPENAI_API_KEY` | _(empty)_ | Browser Use key for OpenAI-backed paths |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | _(empty)_ | Gemini / Google APIs |
| `TWELVE_LABS_API_KEY` / `TWELVELABS_API_KEY` | _(empty)_ | Twelve Labs video understanding |
| `ELEVENLABS_API_KEY` | _(empty)_ | Voice synthesis when enabled |
| `TIKTOK_SESSION_ID` / `INSTAGRAM_SESSION_ID` | _(empty)_ | Live posting sessions when not in dry-run |
| `KILL_SWITCH` | `false` | Emergency stop for browser automation |

## Feature Flags

| Flag | Default | Effect |
|------|---------|--------|
| `FEATURE_STAGE5_MONETIZE` | `false` | Unlocks monetization endpoints and catalog data |
| `DRY_RUN` | `true` | Distribution stays simulated; records marked `dry_run` |
| `KILL_SWITCH` | `false` | Blocks browser automation operations |

## Project Layout

```text
abunnytech/
|-- runtime_dashboard/       # Flask owner UI, templates, fixtures, local API key file
|-- state_api/               # State CRUD API
|-- services/control_plane/  # Pipeline demo + stage routers
|-- apps/m1/api/             # Creator pipeline HTTP API (stages 0-2)
|-- orchestrator/            # Typer CLI
|-- packages/                # contracts, core, browser_runtime, hackathon_pipelines
|-- agents/                  # Stage agent CLIs
|-- stages/                  # Stage implementations (0-5)
|-- scripts/                 # demo.py, smoke.py
|-- tests/                   # Integration and contract tests
|-- integration/             # Handoff manifest, env template, smoke helper
|-- examples/                # Contract fixtures and schemas
|-- stage-0-1-2/             # Archived / snapshot subtree
|-- stage-0-5/               # Archived / snapshot subtree
|-- stage-3-4/               # Archived / snapshot subtree
`-- docs/                    # Architecture and handoffs
```

## Pipeline Stages (Demo Flow)

1. **Identity** - AI persona (voice, avatar, platform targets)
2. **Discovery** - trends, competitors, training signals
3. **Content** - video blueprints and content packages
4. **Distribution** - queue posts (dry-run or live)
5. **Analytics** - metrics, optimization directives, redo queue
6. **Monetization** - optional catalog and brand workflows when enabled

## Stack

- **Python 3.12** and **uv** workspaces
- **FastAPI** + **uvicorn** for HTTP services
- **Flask** + **Jinja2** for the owner dashboard
- **Pydantic v2** for contracts
- **SQLite** (aiosqlite + SQLAlchemy) for persistence
- **Typer** / **Rich** for CLI output
- **browser_runtime** for browser automation abstraction
