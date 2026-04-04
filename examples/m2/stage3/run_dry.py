"""
Stage 3 dry-run demo.

Runs the full distribution pipeline offline — no credentials, no network.
Demonstrates: scheduling → executing → comment triage → DM FSM → persistence.

Usage:
    cd /path/to/abunnytech
    python -m examples.stage3.run_dry
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure UTF-8 output on Windows terminals that default to cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Allow running directly from repo root
sys.path.insert(0, str(Path(__file__).parents[2]))

from browser_runtime.audit import AuditLogger, override_audit
from browser_runtime.types import ProviderType

from agents.stage3_distribution.adapters.mock import MockPlatformAdapter
from agents.stage3_distribution.comment_triage import CommentTriageEngine
from agents.stage3_distribution.contracts import (
    ContentPackage,
    ConversionEvent,
    IdentityMatrix,
    Platform,
)
from agents.stage3_distribution.dm_fsm import DMTriggerFSM
from agents.stage3_distribution.executor import PostingExecutor
from agents.stage3_distribution.persistence import Stage3Store
from agents.stage3_distribution.reply_generator import MockReplyGenerator
from agents.stage3_distribution.scheduler import PlatformTarget, PostingScheduler, PostingWindow
from agents.stage3_distribution.story_planner import StoryPlanner


FIXTURES = Path(__file__).parent / "fixtures"


def load_identity() -> IdentityMatrix:
    data = json.loads((FIXTURES / "identity_matrix.json").read_text(encoding="utf-8"))
    return IdentityMatrix.model_validate(data)


def load_package() -> ContentPackage:
    data = json.loads((FIXTURES / "content_package.json").read_text(encoding="utf-8"))
    return ContentPackage.model_validate(data)


async def main() -> None:
    # Route audit to stdout-friendly log
    override_audit(AuditLogger("./logs/stage3_dry_run.jsonl"))

    identity = load_identity()
    package = load_package()

    print(f"\n{'='*60}")
    print("Stage 3 Dry-Run Demo")
    print(f"Persona: {identity.display_name} | Niche: {identity.niche}")
    print(f"Package: {package.title}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------
    # 1. Scheduler
    # ------------------------------------------------------------------
    print("[ 1 / 5 ] Scheduling posts...")
    targets = [
        PlatformTarget(
            platform=Platform.TIKTOK,
            window=PostingWindow(start_hour=0, end_hour=23),
            max_posts_per_day=3,
        ),
        PlatformTarget(
            platform=Platform.INSTAGRAM,
            window=PostingWindow(start_hour=0, end_hour=23),
            max_posts_per_day=2,
        ),
    ]
    scheduler = PostingScheduler(targets=targets, dry_run=True, sandbox=True)
    scheduled_posts = scheduler.enqueue(package)
    print(f"  → Scheduled {len(scheduled_posts)} posts")
    for sp in scheduled_posts:
        print(f"    • {sp.platform.value} | priority={sp.priority} | id={sp.post_id[:8]}...")

    # ------------------------------------------------------------------
    # 2. Executor
    # ------------------------------------------------------------------
    print("\n[ 2 / 5 ] Executing posts (dry-run)...")
    mock_provider = MagicMock()
    mock_provider.provider_type = ProviderType.MOCK
    adapter = MockPlatformAdapter(provider=mock_provider, dry_run=True)
    executor = PostingExecutor(adapter=adapter, dry_run=True)

    ready = scheduler.dequeue_ready()
    distribution_records = []
    for sp in ready:
        record = await executor.execute_post(sp, identity)
        distribution_records.append(record)
        scheduler.mark_done(sp.post_id, record_id=record.record_id)
        print(f"  → {sp.platform.value}: status={record.status.value} | record={record.record_id[:8]}...")

    # ------------------------------------------------------------------
    # 3. Story planner
    # ------------------------------------------------------------------
    print("\n[ 3 / 5 ] Generating story engagement plans...")
    planner = StoryPlanner()
    for platform in [Platform.TIKTOK, Platform.INSTAGRAM]:
        plan = planner.create_plan(package, platform, identity, dry_run=True)
        print(f"  → {platform.value}: {len(plan.slides)} slides")
        for slide in plan.slides:
            print(f"    slide {slide.slide_index}: {slide.content_type} — {slide.caption[:50]!r}")

    # ------------------------------------------------------------------
    # 4. Comment triage + DM FSM
    # ------------------------------------------------------------------
    print("\n[ 4 / 5 ] Triaging sample comments + running DM FSM...")
    sample_comments = [
        {"comment_id": "c1", "platform": Platform.TIKTOK, "post_id": "p1", "user_id": "alice",
         "text": "omg where can I buy this?? 😭"},
        {"comment_id": "c2", "platform": Platform.TIKTOK, "post_id": "p1", "user_id": "bob",
         "text": "this is so gorgeous and beautiful!!"},
        {"comment_id": "c3", "platform": Platform.TIKTOK, "post_id": "p1", "user_id": "charlie",
         "text": "SCAM SCAM SCAM FAKE FAKE"},
        {"comment_id": "c4", "platform": Platform.TIKTOK, "post_id": "p1", "user_id": "diana",
         "text": "what filter do you use?"},
    ]
    engine = CommentTriageEngine(identity=identity)
    generator = MockReplyGenerator()
    fsm = DMTriggerFSM(identity=identity, reply_generator=generator)

    dm_records = []
    triaged_batch = engine.triage_batch(sample_comments)
    for triaged in triaged_batch:
        reply = generator.generate_reply(triaged, identity)
        conv = fsm.process_comment(triaged)
        dm_records.append(conv)
        print(f"  @{triaged.user_id}: [{triaged.category.value}] → state={conv.fsm_state.value}")
        if reply:
            print(f"    reply: {reply[:70]!r}")

    # ------------------------------------------------------------------
    # 5. Persistence
    # ------------------------------------------------------------------
    print("\n[ 5 / 5 ] Persisting records to SQLite...")
    store = Stage3Store(db_path="./db/stage3_dry_run.db")
    for dr in distribution_records:
        store.save_distribution_record(dr)
    for conv in dm_records:
        store.save_dm_conversation(conv)

    all_dist = store.list_distribution_records()
    all_dm = store.list_dm_conversations()
    print(f"  → Saved {len(all_dist)} distribution records")
    print(f"  → Saved {len(all_dm)} DM conversation records")

    print(f"\n{'='*60}")
    print("Dry-run complete. No real posts were made.")
    print("Audit log: ./logs/stage3_dry_run.jsonl")
    print("DB:        ./db/stage3_dry_run.db")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
