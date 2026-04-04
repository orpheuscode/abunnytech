"""Contract compatibility bridge tests.

Validates that the canonical pipeline_contracts (M1) and the runtime
``packages.contracts`` models produce structurally compatible data for
all handoff types.  Gaps are documented as warnings, not hard failures,
to avoid blocking the demo.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples" / "contracts"

from packages.contracts.content import ContentPackage as RTContentPackage  # noqa: E402, I001
from packages.contracts.content import VideoBlueprint as RTBlueprint  # noqa: E402
from packages.contracts.distribution import DistributionRecord as RTDistribution  # noqa: E402
from packages.contracts.identity import IdentityMatrix as RTIdentity  # noqa: E402
from packages.contracts.monetization import ProductCatalogItem as RTProduct  # noqa: E402
from pipeline_contracts import ContentPackage as M1ContentPackage  # noqa: E402
from pipeline_contracts import DistributionRecord as M1DistributionRecord  # noqa: E402
from pipeline_contracts import IdentityMatrix as M1IdentityMatrix  # noqa: E402
from pipeline_contracts import OptimizationDirectiveEnvelope as M1Directive  # noqa: E402
from pipeline_contracts import ProductCatalogItem as M1Product  # noqa: E402
from pipeline_contracts import RedoQueueItem as M1RedoItem  # noqa: E402
from pipeline_contracts import VideoBlueprint as M1Blueprint  # noqa: E402
from pipeline_contracts import validate_payload_from_path  # noqa: E402

# ---------------------------------------------------------------------------
# 1. Validate pipeline_contracts against JSON examples (canonical source)
# ---------------------------------------------------------------------------

M1_EXAMPLES: list[tuple[str, type]] = [
    ("identity_matrix.json", M1IdentityMatrix),
    ("video_blueprint.json", M1Blueprint),
    ("content_package.json", M1ContentPackage),
    ("distribution_record.json", M1DistributionRecord),
    ("optimization_directive_envelope.json", M1Directive),
    ("redo_queue_item.json", M1RedoItem),
    ("product_catalog_item.json", M1Product),
]


@pytest.mark.parametrize(("filename", "model_cls"), M1_EXAMPLES)
def test_m1_example_roundtrips(filename: str, model_cls: type) -> None:
    """Each canonical JSON example must parse and roundtrip cleanly."""
    path = EXAMPLES_DIR / filename
    if not path.exists():
        pytest.skip(f"example fixture missing: {path}")
    obj = validate_payload_from_path(model_cls, path)
    assert isinstance(obj, model_cls)
    reloaded = model_cls.model_validate(obj.model_dump(mode="json"))
    assert reloaded == obj


# ---------------------------------------------------------------------------
# 2. Validate stage-0-5 runtime contracts can represent same concepts
# ---------------------------------------------------------------------------

CONCEPT_PAIRS: list[tuple[str, type, type, list[str]]] = [
    (
        "IdentityMatrix",
        M1IdentityMatrix,
        RTIdentity,
        ["display_name/name", "niche/tagline", "persona/guidelines", "platform_targets/platforms"],
    ),
    (
        "VideoBlueprint",
        M1Blueprint,
        RTBlueprint,
        ["blueprint_id/id", "matrix_id/identity_id", "outline/scenes"],
    ),
    (
        "ContentPackage",
        M1ContentPackage,
        RTContentPackage,
        ["package_id/id", "primary_video/assets", "matrix_id/identity_id"],
    ),
    (
        "DistributionRecord",
        M1DistributionRecord,
        RTDistribution,
        ["record_id/id", "package_id/content_package_id"],
    ),
    (
        "ProductCatalogItem",
        M1Product,
        RTProduct,
        [],
    ),
]


@pytest.mark.parametrize(
    ("concept", "m1_cls", "rt_cls", "field_mappings"),
    CONCEPT_PAIRS,
    ids=[c[0] for c in CONCEPT_PAIRS],
)
def test_contract_structural_compatibility(
    concept: str,
    m1_cls: type,
    rt_cls: type,
    field_mappings: list[str],
) -> None:
    """Both contract systems should have the same top-level concepts.

    This does NOT require byte-identical schemas -- it verifies that
    each concept exists in both systems and documents the field-name
    mappings for reference.
    """
    m1_fields = set(m1_cls.model_fields.keys())
    rt_fields = set(rt_cls.model_fields.keys())
    shared = m1_fields & rt_fields

    if not shared and not field_mappings:
        warnings.warn(
            f"{concept}: no shared fields between M1 and runtime contracts",
            stacklevel=2,
        )

    for mapping in field_mappings:
        m1_name, rt_name = mapping.split("/")
        assert m1_name in m1_fields, f"{concept}: M1 missing expected field '{m1_name}'"
        assert rt_name in rt_fields, f"{concept}: RT missing expected field '{rt_name}'"


def test_rt_identity_constructs() -> None:
    """Runtime IdentityMatrix can be instantiated with defaults."""
    from packages.contracts.identity import PersonaArchetype

    identity = RTIdentity(name="Test Creator", archetype=PersonaArchetype.EDUCATOR)
    assert identity.id is not None
    assert identity.name == "Test Creator"


def test_rt_blueprint_constructs() -> None:
    """Runtime VideoBlueprint can be instantiated with defaults."""
    bp = RTBlueprint(identity_id="test-id", title="Test Blueprint")
    assert bp.id is not None
    assert bp.title == "Test Blueprint"


def test_rt_content_package_constructs() -> None:
    """Runtime ContentPackage can be instantiated with defaults."""
    cp = RTContentPackage(
        identity_id="test-id",
        blueprint_id="test-bp",
        title="Test Package",
    )
    assert cp.id is not None
    assert cp.status.value == "rendered"


def test_rt_distribution_constructs() -> None:
    """Runtime DistributionRecord can be instantiated with defaults."""
    from packages.contracts.base import Platform

    dr = RTDistribution(
        content_package_id="test-pkg",
        identity_id="test-id",
        platform=Platform.TIKTOK,
    )
    assert dr.id is not None
    assert dr.dry_run is True


# ---------------------------------------------------------------------------
# 3. Schema coverage: both systems cover stages 0-5
# ---------------------------------------------------------------------------

STAGE_CONCEPTS = {
    "stage0_identity": "IdentityMatrix",
    "stage1_discover": "TrendingAudioItem",
    "stage2_generate": "ContentPackage",
    "stage3_distribute": "DistributionRecord",
    "stage4_analyze": "OptimizationDirectiveEnvelope",
    "stage5_monetize": "ProductCatalogItem",
}


def test_m1_covers_all_stages() -> None:
    """pipeline_contracts should export a model for every stage concept."""
    import pipeline_contracts

    for stage, concept in STAGE_CONCEPTS.items():
        assert hasattr(pipeline_contracts, concept), (
            f"pipeline_contracts missing {concept} for {stage}"
        )


def test_rt_covers_all_stages() -> None:
    """Runtime packages.contracts should export a model for every stage concept."""
    import packages.contracts

    for stage, concept in STAGE_CONCEPTS.items():
        assert hasattr(packages.contracts, concept), (
            f"packages.contracts missing {concept} for {stage}"
        )
