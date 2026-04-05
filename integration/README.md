# Integration handoff — pipeline stages 0–2

This folder collects **env templates**, a **smoke script**, and **manifest** data so another team can wire the same HTTP API and Python packages without spelunking the whole monorepo.

## Contents

| Path | Purpose |
| --- | --- |
| `env.example` | Copy to repo root as `.env` for FastAPI (`PIPELINE_*`); includes `PIPELINE_API_BASE` for clients. |
| `smoke_test_api.py` | One-shot HTTP check (stages 0–2 + artifacts). |
| `manifest.json` | Machine-readable pointers to packages and routes. |
| `examples/persona.seed.yaml` | Rich persona sample for `abunny-stage0` CLI (see main repo `agents/stage0_identity`). |

## Quick start

1. **API server** (from repo root, with `.env`):

   ```bash
   cp integration/env.example .env
   uv run uvicorn apps.api.main:app --reload --app-dir stage-0-1-2/apps/api/src
   ```

2. **Smoke test**:

   ```bash
   uv run python integration/smoke_test_api.py --base-url http://127.0.0.1:8000
   ```

3. For the full-stack owner UI (pipeline + API keys), run `uv run python scripts/demo.py` from the repo root and open `http://localhost:8501`.

## Contracts and stages

- Shared models: `stage-0-1-2/packages/contracts` (`IdentityMatrix`, `VideoBlueprint`, `ContentPackage`, …).
- Stage runners: `stage-0-1-2/packages/stage0_identity`, `stage-0-1-2/packages/stage1_discover`, `stage-0-1-2/packages/stage2_generate`.
- Extended Stage 0 compiler CLI: `agents/stage0_identity` (`abunny-stage0 compile …`).

## Copying into another repo

Prefer **git submodule** or **workspace package imports** of `stage-0-1-2/packages/contracts` and `stage-0-1-2/packages/core` at minimum, then depend on stage packages as needed. Use `manifest.json` as the authoritative path list relative to this repository root (`stage_0_1_2_root`).
