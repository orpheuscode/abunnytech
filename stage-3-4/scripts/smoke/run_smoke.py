"""
End-to-end smoke demo for the abunnytech autonomous AI creator pipeline.

Runs the full pipeline in dry-run / mock mode — no credentials required,
no real posts made. Covers all five stages (Stage 5 is gated by feature flag).

Usage:
    cd abunnytech
    python scripts/smoke/run_smoke.py

    # With verbose output:
    python scripts/smoke/run_smoke.py --verbose

    # Override DB path:
    SMOKE_DB=./tmp/smoke.db python scripts/smoke/run_smoke.py

Exit codes:
    0 — all stages passed
    1 — one or more stages failed

Expected output (truncated):
    ============================================================
     abunnytech Smoke Demo — DRY RUN / MOCK MODE
    ============================================================
    [PASS] Stage 0  IdentityMatrix: Bunny 🐰 | niche=fashion
    [PASS] Stage 1  VideoBlueprint: '5 pastel fits for spring' (question hook, 28s)
    [PASS] Stage 2  ContentPackage: '5 pastel fits for spring 🐰' → 2 platforms
    [PASS] Stage 3  Distribution: 2 records (dry_run=True, status=dry_run)
    [PASS] Stage 4  Analytics: 10 metrics | 5 directives | 4 redo items
    [SKIP] Stage 5  Monetize skipped — STAGE5_MONETIZE_ENABLED not set (correct)
    ============================================================
     RESULT: 5/5 stages passed
    ============================================================
"""
from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Fix UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Allow running from repo root without installing packages
_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from packages.evals.fixtures import (
    adapt_s3_to_s4_distribution_record,
    load_s4_distribution_records,
    make_content_package,
    make_identity,
    make_video_blueprint,
)
from packages.evals.validators import assert_no_live_credentials


_BANNER = "=" * 60
_ANALYTICS_FIXTURE = _REPO_ROOT / "tests" / "stage4" / "fixtures" / "sample_analytics.json"


def _section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def _result(stage: int, name: str, detail: str, ok: bool = True) -> None:
    tag = "[PASS]" if ok else "[FAIL]"
    print(f"  {tag} Stage {stage}  {name}: {detail}")


def _skip(stage: int, name: str, reason: str) -> None:
    print(f"  [SKIP] Stage {stage}  {name}: {reason}")


class SmokeResult:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.skipped: list[str] = []

    def ok(self, label: str) -> None:
        self.passed.append(label)

    def fail(self, label: str, reason: str) -> None:
        self.failed.append((label, reason))

    def skip(self, label: str) -> None:
        self.skipped.append(label)

    @property
    def all_passed(self) -> bool:
        return not self.failed


async def run_smoke(db_path: str, verbose: bool = False) -> SmokeResult:
    result = SmokeResult()

    print(_BANNER)
    print(" abunnytech Smoke Demo — DRY RUN / MOCK MODE")
    print(_BANNER)

    # -- Safety: no live credentials
    try:
        assert_no_live_credentials(dict(os.environ))
        if verbose:
            print("  [check] No live credentials detected.")
    except AssertionError as e:
        print(f"  [WARN] {e}")

    # ------------------------------------------------------------------
    # Stage 0 — Identity
    # ------------------------------------------------------------------
    _section("Stage 0 — Identity")
    try:
        identity = make_identity()
        assert identity.persona_name
        assert identity.niche
        assert identity.target_platforms
        assert identity.ai_disclosure_footer
        _result(0, "IdentityMatrix", f"{identity.display_name} | niche={identity.niche}")
        result.ok("stage0_identity")
    except Exception as e:
        _result(0, "IdentityMatrix", f"FAILED: {e}", ok=False)
        result.fail("stage0_identity", str(e))

    # ------------------------------------------------------------------
    # Stage 1 — VideoBlueprint (mock discovery output)
    # ------------------------------------------------------------------
    _section("Stage 1 — Discover & Analyze (mock)")
    try:
        blueprint = make_video_blueprint()
        assert blueprint.blueprint_id
        assert blueprint.hook_style
        assert blueprint.topic
        _result(
            1, "VideoBlueprint",
            f"'{blueprint.topic}' ({blueprint.hook_style} hook, {blueprint.duration_seconds}s)"
        )
        result.ok("stage1_blueprint")
    except Exception as e:
        _result(1, "VideoBlueprint", f"FAILED: {e}", ok=False)
        result.fail("stage1_blueprint", str(e))

    # ------------------------------------------------------------------
    # Stage 2 — ContentPackage (mock generation output)
    # ------------------------------------------------------------------
    _section("Stage 2 — Generate Content (mock)")
    try:
        package = make_content_package(blueprint_id=blueprint.blueprint_id)
        assert package.package_id
        assert package.caption
        assert package.target_platforms
        _result(
            2, "ContentPackage",
            f"'{package.title}' → {len(package.target_platforms)} platforms"
        )
        result.ok("stage2_package")
    except Exception as e:
        _result(2, "ContentPackage", f"FAILED: {e}", ok=False)
        result.fail("stage2_package", str(e))

    # ------------------------------------------------------------------
    # Stage 3 — Distribute & Engage
    # Full dry-run: scheduler → executor → comment triage → DM FSM → persist
    # ------------------------------------------------------------------
    _section("Stage 3 — Distribute & Engage (dry run)")
    try:
        from browser_runtime.audit import AuditLogger, override_audit
        from browser_runtime.types import ProviderType
        from agents.stage3_distribution.adapters.mock import MockPlatformAdapter
        from agents.stage3_distribution.comment_triage import CommentTriageEngine
        from agents.stage3_distribution.contracts import Platform as S3Platform
        from agents.stage3_distribution.dm_fsm import DMTriggerFSM
        from agents.stage3_distribution.executor import PostingExecutor
        from agents.stage3_distribution.persistence import Stage3Store
        from agents.stage3_distribution.reply_generator import MockReplyGenerator
        from agents.stage3_distribution.scheduler import (
            PlatformTarget,
            PostingScheduler,
            PostingWindow,
        )
        from agents.stage3_distribution.story_planner import StoryPlanner

        # Route audit to /dev/null equivalent (suppress noise in smoke output)
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            audit_path = f.name
        override_audit(AuditLogger(audit_path))

        # Scheduler
        targets = [
            PlatformTarget(
                platform=S3Platform.TIKTOK,
                window=PostingWindow(start_hour=0, end_hour=23),
                max_posts_per_day=3,
            ),
            PlatformTarget(
                platform=S3Platform.INSTAGRAM,
                window=PostingWindow(start_hour=0, end_hour=23),
                max_posts_per_day=2,
            ),
        ]
        scheduler = PostingScheduler(targets=targets, dry_run=True, sandbox=True)
        scheduler.enqueue(package)
        ready = scheduler.dequeue_ready()
        assert ready, "Scheduler should enqueue at least one post"

        # Executor
        mock_provider = MagicMock()
        mock_provider.provider_type = ProviderType.MOCK
        adapter = MockPlatformAdapter(provider=mock_provider, dry_run=True)
        executor = PostingExecutor(adapter=adapter, dry_run=True)

        distribution_records = []
        for sp in ready:
            record = await executor.execute_post(sp, identity)
            distribution_records.append(record)
            scheduler.mark_done(sp.post_id, record_id=record.record_id)
            assert record.dry_run is True

        # Comment triage
        engine = CommentTriageEngine(identity=identity)
        generator = MockReplyGenerator()
        fsm = DMTriggerFSM(identity=identity, reply_generator=generator)
        sample_comments = [
            {"comment_id": "c1", "platform": S3Platform.TIKTOK, "post_id": "p1",
             "user_id": "alice", "text": "where can I buy this?"},
            {"comment_id": "c2", "platform": S3Platform.TIKTOK, "post_id": "p1",
             "user_id": "bob", "text": "this is so gorgeous!!"},
        ]
        triaged = engine.triage_batch(sample_comments)
        dm_records = [fsm.process_comment(t) for t in triaged]

        # Persist to tmp DB
        store = Stage3Store(db_path=db_path)
        for dr in distribution_records:
            store.save_distribution_record(dr)
        for conv in dm_records:
            store.save_dm_conversation(conv)

        _result(
            3, "Distribution",
            f"{len(distribution_records)} records (dry_run=True, "
            f"status={distribution_records[0].status.value})"
        )
        _result(
            3, "Comment triage",
            f"{len(triaged)} comments triaged, {len(dm_records)} DM FSM records"
        )
        result.ok("stage3_distribution")

        if verbose:
            for dr in distribution_records:
                print(f"    • {dr.platform.value}: status={dr.status.value} id={dr.record_id[:8]}...")

    except Exception as e:
        _result(3, "Distribution", f"FAILED: {e}", ok=False)
        result.fail("stage3_distribution", str(e))
        distribution_records = []

    # ------------------------------------------------------------------
    # Stage 4 — Analyze & Adapt
    # Use the 10-post fixture dataset (richer than the 2 records from Stage 3)
    # to produce directives and redo queue items.
    # ------------------------------------------------------------------
    _section("Stage 4 — Analyze & Adapt (fixture data)")
    try:
        from agents.stage4_analytics.runner import Stage4Runner
        from agents.stage4_analytics.state_adapter import StateAdapter

        s4_records = load_s4_distribution_records()
        state_adapter = StateAdapter(db_path=db_path.replace(".db", "_s4.db"))
        runner = Stage4Runner(
            dry_run=True,
            state_adapter=state_adapter,
            fixture_path=str(_ANALYTICS_FIXTURE),
            niche="fashion",
        )
        s4_result = await runner.run_weekly(s4_records)

        assert len(s4_result.metrics) == len(s4_records)
        assert s4_result.summary_daily

        _result(
            4, "Analytics",
            f"{len(s4_result.metrics)} metrics | "
            f"{len(s4_result.directives)} directives | "
            f"{len(s4_result.redo_items)} redo items"
        )
        result.ok("stage4_analytics")

        if verbose:
            for d in s4_result.directives[:3]:
                print(f"    • [{d.priority.upper():8s}] {d.directive_type} → {d.target_stage}")
            for item in s4_result.redo_items[:3]:
                print(f"    • [{item.priority.upper():8s}] {item.redo_reason} → {item.target_stage}")

        # Show S3 → S4 boundary adaptation (1 record from stage3 dry run)
        if distribution_records:
            adapted = adapt_s3_to_s4_distribution_record(distribution_records[0])
            assert adapted.content_package_id == distribution_records[0].package_id
            if verbose:
                print(f"    • S3→S4 adapter: package_id={adapted.content_package_id[:8]}...")

    except Exception as e:
        _result(4, "Analytics", f"FAILED: {e}", ok=False)
        result.fail("stage4_analytics", str(e))

    # ------------------------------------------------------------------
    # Stage 5 — Monetize (feature-flagged — must NOT run unless enabled)
    # ------------------------------------------------------------------
    _section("Stage 5 — Monetize (feature flag check)")
    stage5_enabled = os.environ.get("STAGE5_MONETIZE_ENABLED", "false").lower()
    if stage5_enabled in ("1", "true", "yes", "on"):
        _result(5, "Monetize", "STAGE5_MONETIZE_ENABLED=true — SKIPPING live operations")
        _skip(5, "Monetize", "flag enabled but live Shopify ops disabled in smoke mode")
        result.skip("stage5_monetize")
    else:
        _skip(
            5, "Monetize",
            "STAGE5_MONETIZE_ENABLED not set (correct — Stage 5 is feature-flagged)"
        )
        result.skip("stage5_monetize")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total_stages = len(result.passed) + len(result.failed)
    print(f"\n{_BANNER}")
    if result.all_passed:
        print(
            f" RESULT: {len(result.passed)}/{total_stages} stages passed"
            + (f" | {len(result.skipped)} skipped" if result.skipped else "")
        )
    else:
        print(f" RESULT: {len(result.failed)} stage(s) FAILED")
        for label, reason in result.failed:
            print(f"   ✗ {label}: {reason}")
    print(_BANNER)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="abunnytech smoke test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-stage detail")
    args = parser.parse_args()

    db_path = os.environ.get("SMOKE_DB", "./tmp/smoke.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    result = asyncio.run(run_smoke(db_path=db_path, verbose=args.verbose))
    return 0 if result.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
