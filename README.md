# abunnytech — Autonomous AI Creator Pipeline

An end-to-end system that discovers trending products, generates UGC-style marketing reels, posts them to social media through browser automation, measures engagement, and feeds results back into the next generation cycle.

## Architecture

```
                       +-------------------+
                       |  Streamlit Dashboard  :8501
                       +--------+----------+
                                |
          +---------------------+---------------------+
          |                                           |
  +-------v--------+                        +--------v--------+
  | State CRUD API |  :8000                 | Control Plane   |  :8001
  | (FastAPI)      |                        | (FastAPI)       |
  +-------+--------+                        +--------+--------+
          |                                          |
          |     +------------------------------------+
          |     |
  +-------v-----v-------+
  |   Pipeline Stages    |
  |  0: Identity         |  Define the AI persona
  |  1: Discovery        |  Discover trends & competitors
  |  2: Content Gen      |  Generate video blueprints & packages
  |  3: Distribution     |  Distribute to platforms (browser_runtime)
  |  4: Analytics        |  Measure & optimize
  |  5: Monetization     |  Products & brand deals (feature-flagged)
  +----------+-----------+
             |
     +-------v--------+        +-------------+
     | packages.state  |        | browser_    |
     | (SQLite repos)  |        | runtime     |
     +----------------+        +-------------+
```

## Quickstart

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment (all keys optional for dry-run demo)
cp .env.example .env

# 3. Start all services (API + Control Plane + Dashboard)
uv run python scripts/demo.py

# 4. Open the dashboard
#    http://localhost:8501
```

## One-Command Demo

```bash
# Full demo pipeline — no credentials needed
uv run python scripts/demo.py
```

This starts:
- **State CRUD API** on `http://localhost:8000` (with demo seed data)
- **Control Plane** on `http://localhost:8001` (stage routers + `/pipeline/demo`)
- **Streamlit Dashboard** on `http://localhost:8501` (full pipeline visualization)

Trigger the pipeline via the dashboard "Demo Control" page, or:

```bash
curl -X POST http://localhost:8001/pipeline/demo
```

### CLI-Only Demo

```bash
PYTHONPATH=stage-0-5 uv run python -m apps.orchestrator.cli demo
```

## Smoke Tests

```bash
uv run python scripts/smoke.py --verbose
```

Validates: credential safety, feature flags, contract examples, pipeline demo (stages 0-4), full test suite (93 tests), browser runtime (53 tests).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` | When true, no real posts are made |
| `FEATURE_STAGE5_MONETIZE` | `false` | Enable Stage 5 monetization features |
| `DATABASE_URL` | `sqlite+aiosqlite:///./abunnytech.db` | Database connection string |
| `CONTROL_PLANE_PORT` | `8000` | Control plane server port |
| `DASHBOARD_PORT` | `8501` | Streamlit dashboard port |
| `OPENAI_API_KEY` | _(empty)_ | Optional — for live content generation |
| `ELEVENLABS_API_KEY` | _(empty)_ | Optional — for voice synthesis |
| `TIKTOK_SESSION_ID` | _(empty)_ | Optional — for live TikTok posting |
| `INSTAGRAM_SESSION_ID` | _(empty)_ | Optional — for live Instagram posting |
| `KILL_SWITCH` | `false` | Emergency stop for all browser automation |

## Feature Flags

| Flag | Default | Effect |
|------|---------|--------|
| `FEATURE_STAGE5_MONETIZE` | `false` | Unlocks `/monetize/*` endpoints and dashboard page |
| `DRY_RUN` | `true` | All distribution records marked `dry_run`, no real posts |
| `KILL_SWITCH` | `false` | Blocks all browser automation operations |

## Project Structure

```
abunnytech/
├── stage-0-5/              # Integration backbone (stages 0-5, API, dashboard, orchestrator)
│   ├── stages/             # Stage implementations (stage0_identity → stage5_monetize)
│   ├── packages/           # contracts, state, shared config
│   ├── apps/               # api, dashboard, orchestrator
│   └── services/           # control_plane
├── stage-0-1-2/            # M1: canonical contracts, packaged stages 0-2
│   └── packages/contracts/ # pipeline_contracts (source of truth for schemas)
├── stage-3-4/              # M2: browser runtime, stages 3-4 agents, evals
│   └── packages/           # browser_runtime, evals
├── agents/                 # Stage 0-2 agent implementations
├── packages/               # media_pipeline
├── examples/               # Contract JSON fixtures + schema files
├── scripts/                # demo.py, smoke.py
├── tests/                  # Integration tests (contract compatibility)
└── docs/                   # Architecture docs, handoffs
```

## Demo Flow

1. **Stage 0 — Identity**: Creates an AI persona (name, archetype, voice, avatar, platform targets)
2. **Stage 1 — Discovery**: Discovers trending audio, analyzes competitors, builds training manifest
3. **Stage 2 — Content Gen**: Creates a video blueprint and renders a content package
4. **Stage 3 — Distribution**: Posts content to platforms (mock in dry-run), handles comment replies
5. **Stage 4 — Analytics**: Collects performance metrics, generates optimization directives and redo queue
6. **Stage 5 — Monetization** _(opt-in)_: Product catalog, scoring, listing drafts, brand outreach

## Technology Stack

- **Python 3.12** with **uv** workspace management
- **FastAPI** for HTTP APIs
- **Streamlit** for the dashboard
- **Pydantic v2** for contracts and validation
- **SQLite** (via aiosqlite + SQLAlchemy) for persistence
- **Typer** for CLI
- **browser_runtime** for browser automation abstraction
