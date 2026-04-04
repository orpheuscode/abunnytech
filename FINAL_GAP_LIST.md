# Final Gap List — Non-Blocking Unfinished Items

These items are documented for post-hackathon work. None block the demo.

---

## Contract Unification (Priority: Medium)

**Gap:** Three parallel contract systems exist with incompatible field names and ID strategies.

- `pipeline_contracts` (M1): string IDs (`matrix_id`, `blueprint_id`), `extra="forbid"`
- `packages.contracts` (M3 runtime): UUID IDs via `ContractBase`, audit logs, different field shapes
- `stage-3-4/agents/*/contracts.py`: local stubs with their own field names

**Current state:** A compatibility bridge test validates both systems structurally. The demo runs on the M3 runtime contracts. The M1 contracts are the canonical reference.

**Recommendation:** Migrate all stages to `pipeline_contracts` as the single source of truth, then delete the duplicates. Estimated: 2-3 days.

---

## Rich Stage Implementations Not Wired Into Demo (Priority: Low)

**Gap:** The demo path uses `stage-0-5/stages/` implementations with mock adapters. The richer implementations from parallel work are not integrated into the demo pipeline:

- `agents/stage0_identity/` — full CLI with persona YAML compilation
- `agents/stage1_discovery/` — multi-provider discovery with browser automation
- `agents/stage2_generation/` — full media pipeline with ElevenLabs, script adaptation, postproduction
- `stage-3-4/agents/stage3_distribution/` — full posting scheduler, executor, comment triage, DM FSM, story planner
- `stage-3-4/agents/stage4_analytics/` — Stage4Runner with analysis engine and 10-post fixture dataset

**Current state:** These implementations exist and have their own tests. They could be wired in as "live mode" adapters behind the mock adapters.

**Recommendation:** Create adapter selection logic per stage based on `DRY_RUN` flag. When `DRY_RUN=false`, use the rich implementations.

---

## Browser Runtime Live Mode (Priority: Medium)

**Gap:** The `BrowserRuntimePoster` adapter in stage 3 always uses the mock provider. Live posting via `browser_use` provider is stubbed but not tested end-to-end.

**Current state:** The browser_runtime package has full TikTok and Instagram adapters with kill switch and audit logging. These are tested with the mock provider (53 tests pass).

**Recommendation:** Test with real platform credentials in a sandbox account. Requires `playwright install` and valid session tokens.

---

## Database Migration (Priority: Low)

**Gap:** State layer uses SQLite only. Production would need Postgres.

**Current state:** The SQLAlchemy layer is async-compatible. The state models use JSON serialization which would need column mapping for Postgres.

**Recommendation:** Add Postgres connection support to `packages.shared.config` and test with `asyncpg`.

---

## Stage 5 Live Operations (Priority: Low)

**Gap:** Stage 5 monetization uses mock adapters for Shopify, brand outreach drafts, and attribution. No real Shopify integration exists.

**Current state:** All Stage 5 operations produce drafts with `dry_run=True`. The approval workflow gates any real action behind manual review.

**Recommendation:** Implement real Shopify API adapter, real outreach email sender. Keep approval workflow as a safety gate.

---

## Missing Automated Tests

| Area | Gap |
|------|-----|
| Stage-3-4 agents | Tests exist but not in the root pytest path (run separately with `cd stage-3-4`) |
| Dashboard rendering | No automated Streamlit tests (manual verification only) |
| Control plane `/pipeline/demo` | Tested in `test_control_plane.py` but end-to-end only via smoke test |
| Cross-stage integration | No test runs the full pipeline through real stage services (only mock/in-memory) |

---

## PYTHONPATH Complexity (Priority: Low)

**Gap:** The root workspace uses uv-managed packages while `stage-0-5/` uses directory-relative imports (`from packages.state import ...`). This requires setting `PYTHONPATH=stage-0-5` when running from root.

**Recommendation:** Refactor `stage-0-5/packages/` into proper installable Python packages with their own `pyproject.toml` files, then add them as workspace members.

---

## Rate Limiting (Priority: Low)

**Gap:** Rate limiting is mentioned in browser_runtime's adapter config but is not enforced at the pipeline level. The demo path uses mock adapters that have no rate limiting.

**Current state:** The browser_runtime kill switch can halt all operations. Per-platform rate limits are configurable but not active in dry-run mode.

**Recommendation:** Add rate limit middleware to the control plane for production use.
