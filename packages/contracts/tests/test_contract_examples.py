from __future__ import annotations

from pathlib import Path

import pytest

from pipeline_contracts.models import (
    ContentPackage,
    DistributionRecord,
    IdentityMatrix,
    OptimizationDirectiveEnvelope,
    ProductCatalogItem,
    RedoQueueItem,
    VideoBlueprint,
)
from pipeline_contracts.schema_export import HANDOFF_SCHEMA_MODELS, export_handoff_schemas, write_handoff_schema_files
from pipeline_contracts.validation import validate_payload_from_path
from pipeline_contracts.versioning import package_version

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXAMPLES = _REPO_ROOT / "examples" / "contracts"
_SCHEMAS = _EXAMPLES / "schemas"


@pytest.mark.parametrize(
    ("filename", "model_cls"),
    [
        ("identity_matrix.json", IdentityMatrix),
        ("video_blueprint.json", VideoBlueprint),
        ("content_package.json", ContentPackage),
        ("distribution_record.json", DistributionRecord),
        ("optimization_directive_envelope.json", OptimizationDirectiveEnvelope),
        ("redo_queue_item.json", RedoQueueItem),
        ("product_catalog_item.json", ProductCatalogItem),
    ],
)
def test_example_payload_validates(filename: str, model_cls: type) -> None:
    path = _EXAMPLES / filename
    assert path.is_file(), f"missing fixture {path}"
    obj = validate_payload_from_path(model_cls, path)
    assert isinstance(obj, model_cls)
    again = model_cls.model_validate(obj.model_dump(mode="json"))
    assert again == obj


def test_committed_schemas_match_models() -> None:
    """Regenerate to a temp dir and compare to committed ``examples/contracts/schemas``."""
    import json
    import tempfile

    live = export_handoff_schemas()
    assert set(live) == set(HANDOFF_SCHEMA_MODELS.keys()) == {
        p.name.replace(".schema.json", "") for p in _SCHEMAS.glob("*.schema.json")
    }
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        write_handoff_schema_files(tmp)
        for name in live:
            committed = json.loads((_SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
            fresh = json.loads((tmp / f"{name}.schema.json").read_text(encoding="utf-8"))
            assert committed == fresh, f"schema drift for {name}; run: uv run python -m pipeline_contracts"


def test_package_version_readable() -> None:
    v = package_version()
    assert v and v[0].isdigit()
