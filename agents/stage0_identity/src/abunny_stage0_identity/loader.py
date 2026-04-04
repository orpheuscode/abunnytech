from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from abunny_stage0_identity.models_input import PersonaSetup


def load_persona_setup(path: Path) -> PersonaSetup:
    """Load persona setup from a `.yaml` / `.yml` or `.json` file."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        data: Any = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        msg = f"Unsupported persona file type: {suffix} (use .yaml, .yml, or .json)"
        raise ValueError(msg)
    if not isinstance(data, dict):
        msg = "Persona file must contain a JSON object or YAML mapping"
        raise TypeError(msg)
    return PersonaSetup.model_validate(data)
