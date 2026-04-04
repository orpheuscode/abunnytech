"""Contract versioning guidance (no runtime enforcement beyond Pydantic).

The ``pipeline-contracts`` package is the single source of truth for handoff shapes.
Downstream services should pin this package version or vendor the exported JSON Schemas
under ``examples/contracts/schemas/`` and diff on upgrades.

**Rules**

- **Patch** (0.1.x): documentation, descriptions, or JSON Schema metadata only; same
  validation behavior for previously valid payloads.
- **Minor** (0.x.0): additive and backward compatible — new optional fields, new enum
  members, or relaxed validation. Existing payloads remain valid.
- **Major** (x.0.0): breaking — removed or renamed fields, removed enum values, stricter
  validation, or ``extra`` policy changes from ``ignore``/``allow`` to ``forbid`` on a
  model that previously accepted unknown keys.

**Nested payloads**

- :class:`pipeline_contracts.models.common.Envelope` carries a string ``schema_version``
  for opaque ``payload`` dicts inside :class:`~pipeline_contracts.models.directives.OptimizationDirectiveEnvelope`.
  Bump that string when the inner JSON contract changes, even if the outer envelope model is unchanged.

**Regenerating schemas**

After model changes, regenerate files in ``examples/contracts/schemas/`` (see
``pipeline_contracts.schema_export``) and commit them with the package version bump.
"""

from __future__ import annotations

import importlib.metadata

DEFAULT_ENVELOPE_SCHEMA_VERSION = "1"


def package_version() -> str:
    """Installed distribution version of ``pipeline-contracts`` (PEP 440)."""
    return importlib.metadata.version("pipeline-contracts")
