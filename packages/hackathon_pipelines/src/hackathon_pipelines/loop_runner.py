"""Reusable continuous loop runner for the hackathon UGC pipeline.

This module keeps the orchestration generic so the control plane can wire real
Veo/Browser Use assets later. The runner only needs an orchestrator and a
template store; it manages periodic execution, dry-run-friendly placeholders,
and start/stop/status helpers.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, runtime_checkable

from hackathon_pipelines.contracts import OrchestratorRunSummary, VideoTemplateRecord
from hackathon_pipelines.ports import TemplateStorePort


@runtime_checkable
class LoopOrchestratorPort(Protocol):
    async def run_reel_to_template_cycle(self) -> OrchestratorRunSummary: ...

    async def run_product_to_video(
        self,
        *,
        product_image_path: str,
        avatar_image_path: str,
        niche_query: str = "dropship",
    ) -> OrchestratorRunSummary: ...

    async def run_publish_and_feedback(
        self,
        *,
        media_path: str,
        caption: str,
        template_id: str,
        dry_run: bool = True,
    ) -> OrchestratorRunSummary: ...


@dataclass(slots=True)
class LoopRunnerConfig:
    """Configuration for a periodic UGC pipeline loop."""

    interval_seconds: float = 300.0
    initial_delay_seconds: float = 0.0
    max_cycles: int | None = None
    dry_run: bool = True
    stop_on_error: bool = False
    niche_query: str = "dropship"
    caption: str = "Auto-generated UGC"
    workdir: Path = field(default_factory=lambda: Path.cwd() / "data" / "loop_runner")
    product_image_name: str = "product_reference.png"
    avatar_image_name: str = "avatar_reference.png"
    media_name: str = "generated_reel.mp4"


@dataclass(slots=True)
class LoopCycleResult:
    """Result of one loop iteration."""

    cycle_number: int
    started_at: datetime
    finished_at: datetime
    reel_summary: OrchestratorRunSummary | None = None
    product_summary: OrchestratorRunSummary | None = None
    publish_summary: OrchestratorRunSummary | None = None
    template_id: str | None = None
    success: bool = True
    error: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LoopRunnerStatus:
    """Snapshot of the runner state."""

    running: bool
    stop_requested: bool
    cycle_count: int
    last_started_at: datetime | None
    last_finished_at: datetime | None
    next_run_at: datetime | None
    last_error: str | None
    last_cycle: LoopCycleResult | None


class ContinuousLoopRunner:
    """Periodic runner that executes the UGC discovery/generation/publish flow."""

    def __init__(
        self,
        *,
        orchestrator: LoopOrchestratorPort,
        templates: TemplateStorePort,
        config: LoopRunnerConfig | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._templates = templates
        self._config = config or LoopRunnerConfig()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._cycle_count = 0
        self._last_started_at: datetime | None = None
        self._last_finished_at: datetime | None = None
        self._next_run_at: datetime | None = None
        self._last_error: str | None = None
        self._last_cycle: LoopCycleResult | None = None
        self._lock = asyncio.Lock()

    @property
    def config(self) -> LoopRunnerConfig:
        return self._config

    def status(self) -> LoopRunnerStatus:
        return LoopRunnerStatus(
            running=self.is_running,
            stop_requested=self._stop_event.is_set(),
            cycle_count=self._cycle_count,
            last_started_at=self._last_started_at,
            last_finished_at=self._last_finished_at,
            next_run_at=self._next_run_at,
            last_error=self._last_error,
            last_cycle=self._last_cycle,
        )

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> asyncio.Task[None]:
        """Start the background loop and return the created task."""

        if self.is_running:
            msg = "continuous loop runner is already running"
            raise RuntimeError(msg)
        self._stop_event.clear()
        task = asyncio.create_task(self.run_forever(), name="hackathon-loop-runner")
        self._task = task
        return task

    async def stop(self) -> None:
        """Request stop and wait for the background task to exit."""

        self._stop_event.set()
        task = self._task
        if task is None:
            return
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        if self._task is task:
            self._task = None

    async def run_once(self) -> LoopCycleResult:
        """Execute a single discovery -> generation -> publish cycle."""

        async with self._lock:
            return await self._run_cycle()

    async def run_forever(self) -> None:
        """Run until stopped or until `max_cycles` has been reached."""

        try:
            if self._config.initial_delay_seconds > 0:
                await self._sleep_or_stop(self._config.initial_delay_seconds)
            while not self._stop_event.is_set():
                if self._config.max_cycles is not None and self._cycle_count >= self._config.max_cycles:
                    break
                await self.run_once()
                if self._stop_event.is_set():
                    break
                self._next_run_at = datetime.now(UTC) + timedelta(seconds=self._config.interval_seconds)
                await self._sleep_or_stop(self._config.interval_seconds)
        except asyncio.CancelledError:
            self._stop_event.set()
            raise
        finally:
            if self._task is not None and self._task.done():
                self._task = None

    async def _sleep_or_stop(self, seconds: float) -> None:
        if seconds <= 0:
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except TimeoutError:
            return

    def _resolve_asset(self, filename: str) -> Path:
        workdir = self._config.workdir
        workdir.mkdir(parents=True, exist_ok=True)
        path = workdir / filename
        if not path.exists():
            path.write_bytes(b"")
        return path

    def _select_latest_template(self) -> VideoTemplateRecord | None:
        templates = self._templates.list_templates()
        if not templates:
            return None
        return max(
            templates,
            key=lambda t: (
                getattr(t, "updated_at", None) or getattr(t, "created_at", None) or datetime.min.replace(tzinfo=UTC),
                t.template_id,
            ),
        )

    async def _run_cycle(self) -> LoopCycleResult:
        cycle_number = self._cycle_count + 1
        started_at = datetime.now(UTC)
        self._last_started_at = started_at
        self._last_error = None
        notes: list[str] = []
        reel_summary: OrchestratorRunSummary | None = None
        product_summary: OrchestratorRunSummary | None = None
        publish_summary: OrchestratorRunSummary | None = None
        template_id: str | None = None
        success = True
        error: str | None = None

        try:
            reel_summary = await self._orchestrator.run_reel_to_template_cycle()
            notes.extend(reel_summary.notes)

            product_image_path = str(self._resolve_asset(self._config.product_image_name))
            avatar_image_path = str(self._resolve_asset(self._config.avatar_image_name))
            media_path = str(self._resolve_asset(self._config.media_name))

            product_summary = await self._orchestrator.run_product_to_video(
                product_image_path=product_image_path,
                avatar_image_path=avatar_image_path,
                niche_query=self._config.niche_query,
            )
            notes.extend(product_summary.notes)

            latest_template = self._select_latest_template()
            if latest_template is None:
                notes.append("publish_skipped_missing_template")
            else:
                template_id = latest_template.template_id
                publish_summary = await self._orchestrator.run_publish_and_feedback(
                    media_path=media_path,
                    caption=self._config.caption,
                    template_id=template_id,
                    dry_run=self._config.dry_run,
                )
                notes.extend(publish_summary.notes)
        except Exception as exc:  # pragma: no cover - exercised in failure-focused tests
            success = False
            error = str(exc)
            self._last_error = error
            notes.append(error)
            if self._config.stop_on_error:
                self._stop_event.set()

        finished_at = datetime.now(UTC)
        self._last_finished_at = finished_at
        self._cycle_count = cycle_number
        result = LoopCycleResult(
            cycle_number=cycle_number,
            started_at=started_at,
            finished_at=finished_at,
            reel_summary=reel_summary,
            product_summary=product_summary,
            publish_summary=publish_summary,
            template_id=template_id,
            success=success,
            error=error,
            notes=notes,
        )
        self._last_cycle = result
        return result
