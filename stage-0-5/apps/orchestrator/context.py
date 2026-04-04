"""Pipeline execution context passed between stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class PipelineContext:
    """Mutable context that flows through pipeline stages."""

    identity_id: UUID
    current_stage: int = 0
    results: dict[str, Any] = field(default_factory=dict)

    def advance(self) -> None:
        self.current_stage += 1

    def set_result(self, key: str, value: Any) -> None:
        self.results[key] = value
