# Handoff: Main Pipeline Build

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Control Plane (FastAPI)                │
│                   POST /pipeline/demo                    │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ Stage 0  │ Stage 1  │ Stage 2  │ Stage 3  │   Stage 4    │
│ Identity │ Discover │ Generate │ Distrib  │   Analyze    │
│          │          │          │          │              │
│ avatar   │ trending │ blueprint│ post     │ metrics      │
│ voice    │ compete  │ render   │ reply    │ optimize     │
│ persona  │ training │ scenes   │ engage   │ redo queue   │
├──────────┴──────────┴──────────┴──────────┴──────────────┤
│                    Stage 5: Monetize (feature-flagged)    │
├──────────────────────────────────────────────────────────┤
│         packages/contracts (Pydantic v2 models)          │
│         packages/shared (config, db, feature flags)      │
└──────────────────────────────────────────────────────────┘
```

## Contract Flow

```
IdentityMatrix ──────► ALL STAGES
                  │
                  ├──► Stage 1 ──► TrendingAudioItem, CompetitorWatchItem
                  │                TrainingMaterialsManifest
                  │                         │
                  ├──► Stage 2 ◄────────────┘
                  │    VideoBlueprint ──► ContentPackage
                  │                              │
                  ├──► Stage 3 ◄─────────────────┘
                  │    DistributionRecord
                  │              │
                  ├──► Stage 4 ◄─┘
                  │    PerformanceMetricRecord
                  │    OptimizationDirectiveEnvelope ──► Stages 1,2,3
                  │    RedoQueueItem ──► Stages 1,2,3
                  │
                  └──► Stage 5 (feature-flagged)
                       ProductCatalogItem
                       BrandOutreachRecord
                       DMConversationRecord
```

## Integration Points

### For Stage 0 (Identity) consumers:
- Import `IdentityMatrix` from `packages.contracts.identity`
- Call `stages.stage0_identity.service.create_default_identity()` or `create_identity()`
- Identity ID feeds all downstream stages

### For Stage 1 (Discovery) consumers:
- Import from `packages.contracts.discovery`
- Use `stages.stage1_discover.service.DiscoveryService`
- Trending items inform Stage 2 topic selection

### For Stage 2 (Generate) consumers:
- Import from `packages.contracts.content`
- Use `stages.stage2_generate.service.ContentGenerationService`
- `create_blueprint()` → `render_content()` → `ContentPackage`

### For Stage 3 (Distribute) consumers:
- Import from `packages.contracts.distribution`
- Use `stages.stage3_distribute.service.DistributionService`
- Always respects `DRY_RUN` env var

### For Stage 4 (Analyze) consumers:
- Import from `packages.contracts.analytics`
- `OptimizationDirectiveEnvelope` feeds back into Stages 1, 2, 3
- `RedoQueueItem` can target any upstream stage

### For Stage 5 (Monetize) consumers:
- Feature-flagged: `FEATURE_STAGE5_MONETIZE=true` to enable
- All endpoints return 403 when disabled
- Does not affect main demo pipeline

## Database
- SQLite locally via `packages.shared.db`
- All records in `pipeline_records` table (contract_type + stage indexed)
- Audit trail in `audit_logs` table
- Adapter-friendly: change `DATABASE_URL` for Postgres/Supabase
