from __future__ import annotations

import asyncio

import pytest

from hackathon_pipelines.contracts import (
    OrchestratorRunSummary,
    TemplateDisposition,
    VideoTemplateRecord,
)
from hackathon_pipelines.loop_runner import ContinuousLoopRunner, LoopRunnerConfig
from hackathon_pipelines.stores.memory import MemoryTemplateStore


class FakeOrchestrator:
    def __init__(self, templates: MemoryTemplateStore, *, delay: float = 0.0) -> None:
        self.templates = templates
        self.delay = delay
        self.calls: list[object] = []
        self.publish_seen = asyncio.Event()
        self._template_counter = 0

    async def run_reel_to_template_cycle(self) -> OrchestratorRunSummary:
        self.calls.append("reels")
        if self.delay:
            await asyncio.sleep(self.delay)
        self._template_counter += 1
        tpl = VideoTemplateRecord(
            template_id=f"tpl_reel_{self._template_counter}",
            structure_record_id=f"struct_reel_{self._template_counter}",
            veo_prompt_draft="reel prompt",
            disposition=TemplateDisposition.ITERATE,
        )
        self.templates.save_template(tpl)
        return OrchestratorRunSummary(
            run_id="reels",
            reels_scanned=1,
            reels_downloaded=1,
            structures_persisted=1,
            templates_created=1,
            notes=["reels"],
        )

    async def run_product_to_video(
        self,
        *,
        product_image_path: str,
        avatar_image_path: str,
        niche_query: str = "dropship",
    ) -> OrchestratorRunSummary:
        self.calls.append(("product", product_image_path, avatar_image_path, niche_query))
        if self.delay:
            await asyncio.sleep(self.delay)
        self._template_counter += 1
        tpl = VideoTemplateRecord(
            template_id=f"tpl_product_{self._template_counter}",
            structure_record_id=f"struct_product_{self._template_counter}",
            veo_prompt_draft="product prompt",
            disposition=TemplateDisposition.REMAKE,
        )
        self.templates.save_template(tpl)
        return OrchestratorRunSummary(
            run_id="product",
            products_ranked=1,
            templates_created=1,
            generations=1,
            notes=["product"],
        )

    async def run_publish_and_feedback(
        self,
        *,
        media_path: str,
        caption: str,
        template_id: str,
        dry_run: bool = True,
    ) -> OrchestratorRunSummary:
        self.calls.append(("publish", media_path, caption, template_id, dry_run))
        if self.delay:
            await asyncio.sleep(self.delay)
        self.publish_seen.set()
        return OrchestratorRunSummary(
            run_id="publish",
            posts=1,
            analytics_snapshots=1,
            notes=["publish"],
        )


@pytest.mark.asyncio
async def test_run_once_uses_latest_template_and_creates_dry_run_assets(tmp_path) -> None:
    templates = MemoryTemplateStore()
    orchestrator = FakeOrchestrator(templates)
    runner = ContinuousLoopRunner(
        orchestrator=orchestrator,
        templates=templates,
        config=LoopRunnerConfig(workdir=tmp_path, interval_seconds=0.01),
    )

    result = await runner.run_once()

    assert result.success is True
    assert result.cycle_number == 1
    assert result.template_id == "tpl_product_2"
    assert orchestrator.calls == [
        "reels",
        ("product", str(tmp_path / "product_reference.png"), str(tmp_path / "avatar_reference.png"), "dropship"),
        ("publish", str(tmp_path / "generated_reel.mp4"), "Auto-generated UGC", "tpl_product_2", True),
    ]
    assert (tmp_path / "product_reference.png").exists()
    assert (tmp_path / "avatar_reference.png").exists()
    assert (tmp_path / "generated_reel.mp4").exists()
    status = runner.status()
    assert status.cycle_count == 1
    assert status.last_cycle == result
    assert status.last_error is None


@pytest.mark.asyncio
async def test_start_stop_and_periodic_cycles(tmp_path) -> None:
    templates = MemoryTemplateStore()
    orchestrator = FakeOrchestrator(templates, delay=0.01)
    runner = ContinuousLoopRunner(
        orchestrator=orchestrator,
        templates=templates,
        config=LoopRunnerConfig(workdir=tmp_path, interval_seconds=0.01, max_cycles=2),
    )

    task = runner.start()
    await asyncio.wait_for(task, timeout=2)

    status = runner.status()
    assert status.running is False
    assert status.cycle_count == 2
    assert status.stop_requested is False
    assert orchestrator.publish_seen.is_set()

    templates2 = MemoryTemplateStore()
    orchestrator2 = FakeOrchestrator(templates2, delay=0.02)
    runner2 = ContinuousLoopRunner(
        orchestrator=orchestrator2,
        templates=templates2,
        config=LoopRunnerConfig(workdir=tmp_path / "second", interval_seconds=0.5),
    )

    task2 = runner2.start()
    await asyncio.wait_for(orchestrator2.publish_seen.wait(), timeout=2)
    await runner2.stop()

    assert task2.done()
    status2 = runner2.status()
    assert status2.running is False
    assert status2.stop_requested is True
    assert status2.cycle_count >= 1
