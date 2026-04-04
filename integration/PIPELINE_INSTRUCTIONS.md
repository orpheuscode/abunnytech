# Pipeline setup and verification

This document describes how to install, verify, and run the **abunnytech** monorepo after the `integration/hackathon-demo` layout (flattened `agents/`, `packages/`, `apps/m1/`, `tests/`, etc.).

## Prerequisites

- **Python** 3.12 or 3.13 (see root `pyproject.toml`: `requires-python = ">=3.12,<3.14"`).
- **[uv](https://docs.astral.sh/uv/)** for dependency sync and `uv run` (recommended).

Optional for live browser automation:

- **Playwright browsers** after installing the `browser-use` extra:  
  `uv pip install "browser-runtime[browser_use]"` then `playwright install chromium`.

---

## 1. Install and sync

From the repository root:

```bash
uv sync
```

This resolves the workspace (including `hackathon-pipelines`, `browser-runtime`, M1 API packages, agents, etc.) and installs the root project into the virtual environment.

---

## 2. Automated verification (tests)

The following was run successfully on this branch; you can repeat any subset locally.

| Scope | Command |
|--------|---------|
| Hackathon pipelines + browser_runtime + contracts | `uv run pytest packages/hackathon_pipelines/tests packages/browser_runtime/tests packages/pipeline_contracts/tests -q` |
| M1 + agent packages | `uv run pytest tests/m1 agents/stage0_identity/tests agents/stage1_discovery/tests agents/stage2_generation/tests agents/stage3_distribution/tests -q` |
| Runtime service tests | `uv run pytest tests/runtime -q` |
| Stage 3/4 browser + analytics tests | `uv run pytest tests/stage34 -q` |
| **All configured test paths** (root `pyproject.toml` `testpaths`) | `uv run pytest -q` |

Lint (optional):

```bash
uv run ruff check .
```

---

## 3. Hackathon integration stack (dry run, no API keys)

The `hackathon-pipelines` package wires **reel discovery → TwelveLabs-shaped analysis → Gemini template decisions → Veo-shaped generation → social posting tasks**, using **in-memory stores** and **dry-run** adapters when keys are absent.

Quick smoke (prints a run summary dict):

```bash
uv run python -c "import asyncio; from hackathon_pipelines import build_dry_run_stack; print(asyncio.run(build_dry_run_stack().orchestrator.run_reel_to_template_cycle()).model_dump())"
```

Programmatic outline:

```python
import asyncio
from hackathon_pipelines import build_dry_run_stack

async def main():
    stack = build_dry_run_stack()
    summary = await stack.orchestrator.run_reel_to_template_cycle()
    # stack.templates.list_templates() — persisted template records (memory)

asyncio.run(main())
```

For **live** Browser Use, Gemini, TwelveLabs, and Veo, construct the same pipelines with:

- `BrowserProviderFacade(browser_runtime.providers.browser_use.BrowserUseProvider(dry_run=False, ...))`
- `TwelveLabsUnderstanding(dry_run=False)` (requires `TWELVE_LABS_API_KEY` or `TWELVELABS_API_KEY`)
- `GeminiTemplateAgent(dry_run=False)` (requires `GOOGLE_API_KEY` or `GEMINI_API_KEY`)
- `VeoVideoGenerator(dry_run=False)` (same Google key; optional `VEO_MODEL_ID`, default `veo-3.1-generate-preview`)

Browser Use LLM selection (see `packages/browser_runtime/browser_runtime/providers/browser_use.py`):

- Default favors **Gemini** via `ChatGoogle` (`gemini-2.5-flash` unless overridden).
- Set `BROWSER_USE_LLM=openai` (or use a `gpt-…` / `o1` / `o3` model name) for OpenAI.
- Optional: `BROWSER_USE_GEMINI_MODEL`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`.

---

## 4. M1 FastAPI (stages 0–2) and HTTP smoke

Environment template: `integration/env.example` (copy to `.env` at repo root if you use `pipeline_core` settings).

Start the API from the repo root. Root `pyproject.toml` sets `pythonpath` to include `apps/m1/api/src`, so the ASGI app module matches `integration/manifest.json` (`apps/m1/api/src/apps/api/main.py` → import path `apps.api.main`):

```bash
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, with the server running:

```bash
uv run python integration/smoke_test_api.py --base-url http://127.0.0.1:8000
```

Or set `PIPELINE_API_BASE` and run the script without `--base-url`.

---

## 5. Integration manifest

Machine-readable pointers (packages, API entry, smoke script): `integration/manifest.json`.

---

## 6. Troubleshooting

| Symptom | What to check |
|--------|----------------|
| `ModuleNotFoundError` for `hackathon_pipelines` | Run `uv sync` from repo root; ensure `packages/hackathon_pipelines` is listed under `[tool.uv.workspace].members` in root `pyproject.toml`. |
| Browser Use fails on import | Install optional extra: `uv pip install "browser-runtime[browser_use]"` and `playwright install chromium`. |
| TwelveLabs / Gemini / Veo errors in live mode | Confirm API keys and that `dry_run=False` on the corresponding adapter classes. |
| API smoke cannot connect | Confirm uvicorn module path matches your tree and port; check firewall / `PIPELINE_API_BASE`. |

---

## 7. What was verified (checklist)

- [x] `uv sync` completes without resolution errors.
- [x] `pytest` passes for: `hackathon_pipelines`, `browser_runtime`, `pipeline_contracts`, `tests/m1`, agent tests under `agents/*/tests`, `tests/runtime`, `tests/stage34`.
- [x] `build_dry_run_stack().orchestrator.run_reel_to_template_cycle()` completes and returns a non-empty template list in dry run.

For a full green run before a demo, execute:

```bash
uv sync && uv run pytest -q
```

---

*Generated for the hackathon integration branch; update module paths if the API package layout changes.*
