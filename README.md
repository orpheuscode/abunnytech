# abunnytech - Autonomous AI Creator Pipeline

System overview:

> This system is an autonomous UGC ad engine that uses Browser Use, TwelveLabs, Gemini, and Veo 3.1 to generate, post, and optimize product videos on Instagram. In the current codebase, the primary input path is user-provided product uploads into the product catalog. Reel discovery remains in the repo, but AliExpress/product discovery is no longer the primary workflow described here.

Current primary flow:

> User uploads product -> product is stored in `product_catalog` -> Gemini builds prompts from stored video structures/templates -> Veo 3.1 generates the video -> Browser Use posts it to Instagram -> Browser Use engages with comments -> analytics feed back into template reuse/remake/discard decisions.

## Main Services

```text
Flask owner dashboard   :8501
State API               :8000
Control plane           :8001
SQLite                  data/hackathon_pipelines.sqlite3
```

Main implementation paths:

- `packages/hackathon_pipelines/src/hackathon_pipelines/pipelines/reel_discovery.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/pipelines/video_generation.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/pipelines/db_to_video_generation.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/pipelines/social_media.py`
- `packages/hackathon_pipelines/src/hackathon_pipelines/adapters/live_api.py`
- `services/control_plane/app.py`
- `runtime_dashboard/flask_owner_app.py`

## Quickstart

### Full stack

```bash
uv sync
cp .env.example .env
uv run python -m scripts.demo
```

Open:

- Dashboard: `http://localhost:8501`
- State API docs: `http://localhost:8000/docs`
- Control plane docs: `http://localhost:8001/docs`

### Primary product-input API

```bash
curl -X POST http://localhost:8000/product_catalog \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "My Product",
    "description": "Short description for the offer",
    "price_cents": 4900,
    "url": "https://store.example.com/product",
    "image_url": "/static/uploads/products/product-example.png"
  }'
```

### Run services separately

```bash
uv run python -m uvicorn state_api.main:app --host 0.0.0.0 --port 8000
```

```bash
uv run python -m uvicorn services.control_plane.app:app --host 0.0.0.0 --port 8001
```

```bash
DASHBOARD_PORT=8501 uv run python -m runtime_dashboard.flask_owner_app
```

## Dashboard Runtime Setup

The dashboard stores runtime secrets and browser config in `runtime_dashboard/.owner_secrets.json`.

Supported runtime setup:

- `BROWSER_USE_API_KEY`
- `GOOGLE_API_KEY`
- `TWELVE_LABS_API_KEY`
- `BROWSER_USE_CDP_URL`
- `CHROME_EXECUTABLE_PATH`
- `CHROME_USER_DATA_DIR`
- `CHROME_PROFILE_DIRECTORY`

Notes:

- exported env vars are used first
- saved dashboard settings are used next
- local Chrome can be auto-detected
- you can type a profile name like `Profile 9` or `Default`
- `Launch Local Chrome + Save CDP` opens a visible Chrome window and saves the CDP URL
- live Browser Use defaults to visible windows unless `BROWSER_USE_HEADLESS=true`

## Core Control-Plane Endpoints

```bash
# Legacy full discovery -> structure -> generation pipeline
curl -X POST http://localhost:8001/pipeline/demo
```

```bash
# Primary current path: generate a new video from the uploaded product catalog + saved video-structure/template DB
curl -X POST http://localhost:8001/pipeline/generate-video \
  -H 'Content-Type: application/json' \
  -d '{"dry_run": true}'
```

```bash
# Inspect the latest run
curl http://localhost:8001/pipeline/latest-run
```

```bash
# Post the latest ready run
curl -X POST http://localhost:8001/pipeline/post-latest \
  -H 'Content-Type: application/json' \
  -d '{"dry_run": true}'
```

```bash
# Re-run comment engagement for the latest post
curl -X POST http://localhost:8001/pipeline/engage-latest \
  -H 'Content-Type: application/json' \
  -d '{"dry_run": true}'
```

```bash
# List posted records with engagement summaries
curl http://localhost:8001/pipeline/posts
```

```bash
# Demo mode: start the three parallel background lanes
curl -X POST http://localhost:8001/pipeline/demo-mode \
  -H 'Content-Type: application/json' \
  -d '{"dry_run": true}'
```

Demo mode currently starts three parallel lanes:

1. `reel discovery -> video structure`
2. `video structure -> video gen + instagram posting`
3. `comment engagement`

The repo still contains discovery-oriented paths, but the product-upload flow above is the primary path reflected in the active dashboard and current usage.

## Dashboard Demo Controls

The dashboard exposes the current active control flow:

1. `Run Pipeline`
2. `Generate Video From Structure DB`
3. `Post Latest Reel`
4. `Engage Latest IG Comments`
5. `Launch Instant Demo Mode`

`Launch Instant Demo Mode` starts the three background lanes above.

## Tests

```bash
uv run pytest packages/hackathon_pipelines/tests -q
uv run pytest tests/runtime -q
```

## Useful Environment Variables

| Variable | Description |
|----------|-------------|
| `DRY_RUN` | Keeps posting/generation in dry-run mode |
| `BROWSER_USE_API_KEY` | Browser Use API key |
| `GOOGLE_API_KEY` | Gemini / Veo API key |
| `TWELVE_LABS_API_KEY` | TwelveLabs API key |
| `BROWSER_USE_CDP_URL` | Connect to an existing visible Chrome debug instance |
| `CHROME_EXECUTABLE_PATH` | Local Chrome binary path |
| `CHROME_USER_DATA_DIR` | Local Chrome user-data root |
| `CHROME_PROFILE_DIRECTORY` | Chrome profile name such as `Profile 9` |
| `DASHBOARD_PORT` | Owner dashboard port |
| `OWNER_DASHBOARD_SECRET` | Flask session secret |

## Project Layout

```text
abunnytech/
|-- runtime_dashboard/       # Flask owner UI
|-- state_api/               # State CRUD API
|-- services/control_plane/  # Control plane endpoints
|-- packages/browser_runtime/
|-- packages/hackathon_pipelines/
|-- scripts/                 # demo launcher and helper scripts
`-- tests/
```
