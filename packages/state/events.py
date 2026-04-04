"""Lightweight event bus and job-registration primitives.

These are intentionally simple – enough for demo orchestration between
pipeline stages without pulling in Celery/Dramatiq/etc.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """Async publish / subscribe within a single process."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, event: str, handler: EventHandler) -> None:
        self._handlers[event].append(handler)

    def off(self, event: str, handler: EventHandler) -> None:
        self._handlers[event].remove(handler)

    async def emit(self, event: str, **kwargs: Any) -> None:
        for handler in self._handlers.get(event, []):
            await handler(**kwargs)

    async def emit_concurrent(self, event: str, **kwargs: Any) -> None:
        handlers = self._handlers.get(event, [])
        if handlers:
            await asyncio.gather(*(h(**kwargs) for h in handlers))


class JobRegistry:
    """Named-job registry so stages can advertise runnable tasks."""

    def __init__(self) -> None:
        self._jobs: dict[str, EventHandler] = {}

    def register(self, name: str, handler: EventHandler) -> None:
        self._jobs[name] = handler

    async def run(self, name: str, **kwargs: Any) -> Any:
        if name not in self._jobs:
            raise KeyError(f"Job {name!r} not registered")
        return await self._jobs[name](**kwargs)

    def list_jobs(self) -> list[str]:
        return sorted(self._jobs)
