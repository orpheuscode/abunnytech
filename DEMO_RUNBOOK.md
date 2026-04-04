# Demo Runbook — Recorded Submission

This runbook provides the exact sequence to demonstrate the abunnytech AI Creator Pipeline for a hackathon recording.

**Estimated runtime:** 5-8 minutes

---

## Prerequisites

```bash
uv sync
cp .env.example .env
```

Verify: `uv run python scripts/smoke.py` should report 8/8 checks passed.

---

## Path A: Full Demo (API + Dashboard)

### 1. Start Services (one command)

```bash
uv run python scripts/demo.py
```

Wait for the "Services running" banner. You should see:
- API at http://localhost:8000
- Control Plane at http://localhost:8001
- Dashboard at http://localhost:8501

### 2. Open Dashboard

Navigate to **http://localhost:8501** in a browser.

### 3. Walk Through Pipeline Stages

**Stage 0 — Identity** (sidebar: "Identity")
- Show the seeded identity "TechTok Sarah" with archetype, tagline, platform targets
- Point out the AI disclosure field

**Stage 1 — Discovery** (sidebar: "Discovery")
- Show trending audio items with platform, usage count, trend score
- Show competitor watchlist

**Stage 2 — Content** (sidebar: "Content")
- Show video blueprint with script, duration, status
- Show rendered content package with caption, hashtags

**Stage 3 — Distribution** (sidebar: "Distribution")
- Show distribution record with platform, status, dry_run flag
- Emphasize: "All posts are dry-run — no real social media writes"

**Stage 4 — Analytics** (sidebar: "Analytics")
- Show performance metrics (views, likes, comments, shares)
- Show optimization directives
- Show redo queue items

**Stage 5 — Monetization** (sidebar: "Monetization")
- Show that it displays "Feature disabled" or limited view
- Mention: "Stage 5 is feature-flagged and disabled by default"

### 4. Trigger Live Pipeline Run

Go to **"Demo Control"** in the sidebar.
- Click "Run Demo Pipeline" or use:
  ```bash
  curl -X POST http://localhost:8001/pipeline/demo
  ```
- Show the JSON response with all 5 stages completed
- Refresh dashboard pages to see new data

### 5. Show Health Endpoint

```bash
curl http://localhost:8001/health
```

Expected:
```json
{"status": "healthy", "dry_run": true, "stage5_monetize": false}
```

### 6. Stop Services

Press `Ctrl+C` in the terminal running `demo.py`.

---

## Path B: CLI-Only Demo (Fallback)

Use this if the API/dashboard doesn't start or if you prefer a terminal demo.

### 1. Run Pipeline via CLI

```bash
# Windows (PowerShell)
$env:PYTHONPATH = "stage-0-5"; uv run python -m apps.orchestrator.cli demo

# macOS/Linux
PYTHONPATH=stage-0-5 uv run python -m apps.orchestrator.cli demo
```

### 2. Show Output

The CLI prints a JSON object with all stages:
- `stage0_identity` — identity_id and name
- `stage1_discover` — audio_id and title
- `stage2_generate` — blueprint_id and package_id
- `stage3_distribute` — distribution_id and status (dry_run)
- `stage4_analyze` — directive_id and redo_id

### 3. Run Smoke Test

```bash
uv run python scripts/smoke.py --verbose
```

Show all 8 checks passing.

---

## Path C: Enable Stage 5 (Optional Extension)

### 1. Set Feature Flag

Edit `.env`:
```
FEATURE_STAGE5_MONETIZE=true
```

### 2. Restart Services

```bash
uv run python scripts/demo.py
```

### 3. Show Monetization Page

Navigate to the "Monetization" page in the dashboard — it should now be active with product catalog, brand outreach, and listing draft features.

### 4. Verify Health

```bash
curl http://localhost:8001/health
```

Expected: `"stage5_monetize": true`

---

## Key Talking Points

1. **Closed-loop system**: Product discovery -> content generation -> distribution -> analytics -> optimization -> repeat
2. **Dry-run safe**: All browser automation is mocked, no real social media writes without credentials
3. **Feature-flagged**: Stage 5 (monetization) is disabled by default, can be toggled on
4. **Contract-driven**: Canonical Pydantic models define every stage boundary
5. **Browser automation ready**: browser_runtime package supports TikTok, Instagram, analytics adapters with kill switch and audit logging
6. **Full observability**: Dashboard shows every stage's data, control surface triggers the pipeline
