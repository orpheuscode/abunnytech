from __future__ import annotations

import json
from pathlib import Path

import pytest

from abunny_stage0_identity.loader import load_persona_setup


def test_load_yaml(tmp_path: Path) -> None:
    p = tmp_path / "p.yaml"
    p.write_text(
        "display_name: A\nniche: testing\npersonality:\n  traits: [x]\n",
        encoding="utf-8",
    )
    s = load_persona_setup(p)
    assert s.display_name == "A"
    assert s.niche == "testing"
    assert s.personality.traits == ["x"]


def test_load_json(tmp_path: Path) -> None:
    p = tmp_path / "p.json"
    p.write_text(
        json.dumps({"display_name": "B", "niche": "n2"}),
        encoding="utf-8",
    )
    s = load_persona_setup(p)
    assert s.display_name == "B"


def test_rejects_bad_suffix(tmp_path: Path) -> None:
    p = tmp_path / "p.txt"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        load_persona_setup(p)
