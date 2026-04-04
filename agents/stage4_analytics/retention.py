"""
Retention graph parser interface and fixture-driven mock.

Platform analytics exports include a time-series retention curve: at each
second of the video, what fraction of viewers are still watching?

Stage 4 uses the parsed curve to compute:
  - drop_off_second: when viewer loss accelerates
  - hook_score:      quality of the first 3 seconds
  - midroll_score:   whether the middle third holds attention
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RetentionCurve:
    """
    Parsed retention data for a single video post.

    retention_by_second: index i → fraction (0.0–1.0) still watching at second i
    """
    post_id: str
    duration_seconds: int
    retention_by_second: list[float]   # length = duration_seconds + 1

    @property
    def hook_score(self) -> float:
        """Average retention across first 3 seconds (0–1). Higher is better."""
        if len(self.retention_by_second) < 4:
            return self.retention_by_second[-1] if self.retention_by_second else 0.0
        return sum(self.retention_by_second[1:4]) / 3

    @property
    def completion_rate(self) -> float:
        """Fraction reaching the final second."""
        return self.retention_by_second[-1] if self.retention_by_second else 0.0

    @property
    def drop_off_second(self) -> int:
        """
        First second where retention drops by more than 10 pp in a single step.
        Returns -1 if no such drop exists.
        """
        for i in range(1, len(self.retention_by_second)):
            drop = self.retention_by_second[i - 1] - self.retention_by_second[i]
            if drop > 0.10:
                return i
        return -1

    @property
    def midroll_score(self) -> float:
        """Average retention over the middle third of the video."""
        n = len(self.retention_by_second)
        if n < 3:
            return self.completion_rate
        start = n // 3
        end = 2 * n // 3
        mid = self.retention_by_second[start:end]
        return sum(mid) / len(mid) if mid else 0.0


class AbstractRetentionParser(ABC):
    """Interface for parsing platform-specific retention curve exports."""

    @abstractmethod
    def parse(self, raw: dict[str, Any]) -> RetentionCurve:
        """
        Parse a platform-specific retention payload into a RetentionCurve.
        """

    @abstractmethod
    async def fetch_curve(self, post_id: str, platform: str) -> RetentionCurve | None:
        """
        Fetch and parse the retention curve for a given post.
        Returns None if unavailable.
        """


class MockRetentionParser(AbstractRetentionParser):
    """
    Fixture-driven retention parser.

    Loads from a JSON file whose top-level key is "curves", each entry having:
      {post_id, duration_seconds, retention_by_second: [float, ...]}

    Falls back to a synthetic smooth-decay curve for unknown post_ids.
    """

    def __init__(self, fixture_path: str | None = None) -> None:
        self._fixture_path = Path(fixture_path) if fixture_path else None
        self._store: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if self._fixture_path and self._fixture_path.exists():
            raw = json.loads(self._fixture_path.read_text(encoding="utf-8"))
            for entry in raw.get("curves", []):
                self._store[entry["post_id"]] = entry
        self._loaded = True

    def parse(self, raw: dict[str, Any]) -> RetentionCurve:
        curve = raw.get("retention_by_second", [])
        if not curve:
            # synthesise a plausible exponential decay
            duration = raw.get("duration_seconds", 30)
            import math
            curve = [round(math.exp(-0.05 * t), 3) for t in range(duration + 1)]
        return RetentionCurve(
            post_id=raw["post_id"],
            duration_seconds=raw.get("duration_seconds", len(curve) - 1),
            retention_by_second=curve,
        )

    async def fetch_curve(self, post_id: str, platform: str) -> RetentionCurve | None:
        self._load()
        if post_id in self._store:
            return self.parse(self._store[post_id])
        # Synthetic fallback with hook-drop at second 3
        import hashlib
        import math
        seed = int(hashlib.md5(post_id.encode()).hexdigest()[:4], 16) % 100
        duration = 30
        curve = []
        for t in range(duration + 1):
            base = math.exp(-0.04 * t)
            hook_drop = 0.15 if t == 3 else 0.0
            curve.append(round(max(0.0, base - hook_drop - (seed / 5000) * t), 3))
        return RetentionCurve(
            post_id=post_id,
            duration_seconds=duration,
            retention_by_second=curve,
        )
