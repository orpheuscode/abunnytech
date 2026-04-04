# Stages 0–1–2 bundle

This folder contains **one machine’s slice** of the creator pipeline so other terminals can integrate without hunting through unrelated packages.

| Path | Role |
| --- | --- |
| `packages/contracts` | Canonical Pydantic handoff models |
| `packages/core` | Settings, SQLite, audit, repository |
| `packages/stage0_identity` | Identity + training manifest service |
| `packages/stage1_discover` | Discover/analyze → `VideoBlueprint` |
| `packages/stage2_generate` | Generate → `ContentPackage` + media path |
| `apps/api` | FastAPI control plane |
| `apps/dashboard` | Streamlit demo client |
| `tests/` | API + package tests for this bundle |

**Repo root** still holds shared workspace members (`agents/`, `packages/media_pipeline/`, …). From the repository root, run `uv sync` and use paths under `stage-0-1-2/` as in `integration/manifest.json`.
