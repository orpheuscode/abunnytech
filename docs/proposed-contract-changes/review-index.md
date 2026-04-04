# Proposed contract changes — review index

Use this list when reviewing PRs that touch `packages/contracts/**`, `examples/contracts/**`, or handoff documentation.

## Checklist

1. **Semver:** Does `packages/contracts/pyproject.toml` need a patch/minor/major bump per `pipeline_contracts.versioning`?
2. **Schemas:** Run `uv run python -m pipeline_contracts` and commit updated `examples/contracts/schemas/*.schema.json` if models changed.
3. **Examples:** Add or update matching JSON under `examples/contracts/` so `test_contract_examples` stays green.
4. **Consumers:** Grep for `model_validate` / artifact keys in stage packages and workers; note any migration steps in the PR description.
5. **Envelope payloads:** If only inner directive JSON changes, bump `Envelope.schema_version` and document the new keys in the PR.

## Open proposals

_None — add a row here when a change is drafted but not merged._

| ID | Summary | Author | Status |
|----|---------|--------|--------|
