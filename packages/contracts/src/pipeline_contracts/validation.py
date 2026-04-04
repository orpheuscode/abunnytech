"""Load and validate handoff payloads without embedding pipeline business rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def validate_payload(model_cls: type[T], data: dict[str, Any] | str | bytes) -> T:
    """Parse ``data`` as JSON (if str/bytes) or validate a dict against ``model_cls``."""
    if isinstance(data, dict):
        return model_cls.model_validate(data)
    if isinstance(data, (bytes, bytearray)):
        return model_cls.model_validate_json(data)
    return model_cls.model_validate_json(data)


def validate_payload_from_path(model_cls: type[T], path: Path) -> T:
    """Read UTF-8 JSON from ``path`` and validate."""
    raw = path.read_text(encoding="utf-8")
    return validate_payload(model_cls, raw)


def dump_example(model: BaseModel) -> str:
    """Serialize a model to pretty JSON (for fixtures and golden tests)."""
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
