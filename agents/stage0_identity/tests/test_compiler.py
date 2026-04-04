from __future__ import annotations

import pytest
from pydantic import ValidationError

from abunny_stage0_identity.compiler import IdentityMatrixCompiler, parse_platform_targets
from abunny_stage0_identity.models_input import PersonaSetup
from pipeline_contracts.models import IdentityMatrix


def _minimal_setup() -> PersonaSetup:
    return PersonaSetup.model_validate(
        {
            "display_name": "Test Creator",
            "niche": "  DIY crafts  ",
            "product_categories": ["Glue", "glue", "Paper"],
            "personality": {"traits": ["kind"], "energy": "low"},
            "posting_cadence": {"posts_per_week": 2, "best_windows_utc": [" 9-10 "]},
            "dm_trigger_rules": [{"match": " hi ", "action": " wave ", "notes": " x "}],
        }
    )


def test_normalize_dedupes_categories() -> None:
    c = IdentityMatrixCompiler(_minimal_setup(), dry_run=True)
    assert c.normalize_product_categories() == ["Glue", "Paper"]


def test_compile_produces_valid_contract() -> None:
    c = IdentityMatrixCompiler(_minimal_setup(), dry_run=True)
    im = c.compile_identity_matrix("im_fixed_test")
    parsed = IdentityMatrix.model_validate(im.model_dump(mode="json"))
    assert parsed.matrix_id == "im_fixed_test"
    assert "niche:" in parsed.persona.topics[0]
    assert parsed.avatar.provider == "higgsfield"
    assert parsed.voice.provider == "elevenlabs"


def test_non_dry_run_requires_integration_hints() -> None:
    c = IdentityMatrixCompiler(_minimal_setup(), dry_run=False)
    with pytest.raises(ValueError, match="Higgsfield"):
        c.compile_identity_matrix("im_x")


def test_persona_setup_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        PersonaSetup.model_validate({"display_name": "  ", "niche": "n"})


def test_parse_platform_targets_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown platform"):
        parse_platform_targets(["tiktok", "not_a_platform"])


def test_parse_platform_targets_defaults_when_empty() -> None:
    p = parse_platform_targets([])
    assert len(p) == 2
