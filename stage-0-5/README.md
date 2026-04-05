# abunnytech — Autonomous AI Creator Pipeline

An end-to-end autonomous AI content creator system built for hackathon demo.

## Quick Start

```bash
# Install dependencies (requires Python 3.12+ and uv)
uv sync

# Or with pip
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env

# Run the control plane
python -m services.control_plane

# In another terminal, run the owner dashboard (from monorepo root)
# uv run python -m runtime_dashboard.flask_owner_app
# Or: uv run python scripts/demo.py

# Or hit the one-click demo endpoint
curl -X POST http://localhost:8000/pipeline/demo | python -m json.tool
```

## Pipeline Stages

| Stage | Name | Description | Demo Priority |
|-------|------|-------------|---------------|
| 0 | **Identity** | Avatar + voice pack creation | 1 |
| 1 | **Discover** | Viral trend discovery & competitor analysis | 4 |
| 2 | **Generate** | Video blueprint creation & rendering | 2 |
| 3 | **Distribute** | Platform posting & comment engagement | 3 |
| 4 | **Analyze** | Performance metrics & optimization | 6 |
| 5 | **Monetize** | Product catalog & brand outreach | Feature-flagged |

## API Endpoints

- `GET /` — Service info
- `GET /health` — Health check
- `POST /pipeline/demo` — **One-click full demo pipeline**
- `POST /identity/default` — Create demo identity
- `POST /discover/trending` — Discover trends
- `POST /generate/blueprint` — Create video blueprint
- `POST /generate/render/{id}` — Render content
- `POST /distribute/post` — Post content (dry-run by default)
- `POST /analyze/collect/{id}` — Collect metrics

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
abunnytech/
├── packages/
│   ├── contracts/       # Pydantic v2 data contracts (read-only)
│   └── shared/          # Config, DB, feature flags
├── stages/
│   ├── stage0_identity/ # Persona creation
│   ├── stage1_discover/ # Trend & competitor discovery
│   ├── stage2_generate/ # Content generation & rendering
│   ├── stage3_distribute/ # Platform posting & engagement
│   ├── stage4_analyze/  # Analytics & optimization
│   └── stage5_monetize/ # Monetization (feature-flagged)
├── services/
│   ├── control_plane/   # FastAPI orchestrator
│   └── dashboard/       # (removed — use runtime_dashboard/ Flask app at repo root)
├── tests/               # pytest suite
├── status/              # Build status tracking
└── docs/                # Architecture & handoff docs
```

## Configuration

All config via environment variables (see `.env.example`):

- `DRY_RUN=true` — Safety switch, prevents real platform posting
- `FEATURE_STAGE5_MONETIZE=false` — Enable/disable monetization stage
- `DATABASE_URL` — SQLite by default, swap to Postgres for production
