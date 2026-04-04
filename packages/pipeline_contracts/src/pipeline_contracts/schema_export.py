"""JSON Schema export for handoff contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pipeline_contracts.models import (
    ContentPackage,
    DistributionRecord,
    IdentityMatrix,
    OptimizationDirectiveEnvelope,
    ProductCatalogItem,
    RedoQueueItem,
    VideoBlueprint,
)

# Top-level handoff models whose schemas are published for integrators.
HANDOFF_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "IdentityMatrix": IdentityMatrix,
    "VideoBlueprint": VideoBlueprint,
    "ContentPackage": ContentPackage,
    "DistributionRecord": DistributionRecord,
    "OptimizationDirectiveEnvelope": OptimizationDirectiveEnvelope,
    "RedoQueueItem": RedoQueueItem,
    "ProductCatalogItem": ProductCatalogItem,
}


def export_handoff_schemas() -> dict[str, dict[str, Any]]:
    """Return model title -> JSON Schema dict for all published handoff types."""
    return {name: cls.model_json_schema() for name, cls in HANDOFF_SCHEMA_MODELS.items()}


def export_handoff_schemas_json(*, indent: int = 2) -> str:
    """Single JSON object containing all handoff schemas (for tooling)."""
    return json.dumps(export_handoff_schemas(), indent=indent)


def write_handoff_schema_files(output_dir: Path) -> None:
    """Write one ``<Name>.schema.json`` per handoff model into ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, schema in export_handoff_schemas().items():
        path = output_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def dump_schemas_json() -> str:
    """Backward-compatible alias: same as ``export_handoff_schemas_json``."""
    return export_handoff_schemas_json()


def export_core_schemas() -> dict[str, dict[str, Any]]:
    """Subset export for legacy callers (identity → content chain)."""
    core = ("IdentityMatrix", "VideoBlueprint", "ContentPackage")
    full = export_handoff_schemas()
    return {k: full[k] for k in core}


def _default_repo_schemas_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "examples" / "contracts" / "schemas"


def main() -> None:
    """CLI: ``python -m pipeline_contracts.schema_export`` writes repo schema files."""
    write_handoff_schema_files(_default_repo_schemas_dir())


if __name__ == "__main__":
    main()
