"""Tests for Stage3Store (SQLite persistence)."""
from __future__ import annotations

from datetime import datetime

import pytest

from ..contracts import (
    CommentCategory,
    DistributionRecord,
    DistributionStatus,
    DMConversationRecord,
    DMState,
    Platform,
)
from ..persistence import Stage3Store


@pytest.fixture
def store(tmp_path) -> Stage3Store:
    return Stage3Store(db_path=str(tmp_path / "test_stage3.db"))


def _make_dist_record(
    package_id: str = "pkg-001",
    platform: Platform = Platform.TIKTOK,
    status: DistributionStatus = DistributionStatus.DRY_RUN,
) -> DistributionRecord:
    return DistributionRecord(
        package_id=package_id,
        identity_id="identity-001",
        platform=platform,
        status=status,
        caption_used="Test caption",
        hashtags_used=["#test"],
        dry_run=True,
        posted_at=datetime(2026, 4, 4, 12, 0, 0) if status == DistributionStatus.POSTED else None,
    )


def _make_dm_record(
    platform: Platform = Platform.TIKTOK,
    user_id: str = "user-001",
    state: DMState = DMState.REPLY_PLANNED,
) -> DMConversationRecord:
    return DMConversationRecord(
        platform=platform,
        post_id="post-001",
        comment_id="comment-001",
        user_id=user_id,
        comment_text="where is the link?",
        comment_category=CommentCategory.TRIGGER_DM,
        trigger_keyword="link",
        fsm_state=state,
        reply_text="Hey! DM me 🐰",
        dry_run=True,
    )


# ---------------------------------------------------------------------------
# DistributionRecord
# ---------------------------------------------------------------------------


def test_save_and_get_distribution_record(store):
    record = _make_dist_record()
    store.save_distribution_record(record)

    retrieved = store.get_distribution_record(record.record_id)
    assert retrieved is not None
    assert retrieved.record_id == record.record_id
    assert retrieved.package_id == record.package_id
    assert retrieved.platform == record.platform
    assert retrieved.status == record.status


def test_get_distribution_record_not_found(store):
    assert store.get_distribution_record("nonexistent") is None


def test_upsert_distribution_record(store):
    record = _make_dist_record()
    store.save_distribution_record(record)

    updated = record.model_copy(update={"status": DistributionStatus.POSTED})
    store.save_distribution_record(updated)

    retrieved = store.get_distribution_record(record.record_id)
    assert retrieved.status == DistributionStatus.POSTED


def test_list_distribution_records_by_platform(store):
    store.save_distribution_record(_make_dist_record(platform=Platform.TIKTOK))
    store.save_distribution_record(_make_dist_record(platform=Platform.INSTAGRAM))

    results = store.list_distribution_records(platform=Platform.TIKTOK)
    assert len(results) == 1
    assert results[0].platform == Platform.TIKTOK


def test_list_distribution_records_by_package(store):
    store.save_distribution_record(_make_dist_record(package_id="pkg-A"))
    store.save_distribution_record(_make_dist_record(package_id="pkg-B"))

    results = store.list_distribution_records(package_id="pkg-A")
    assert len(results) == 1
    assert results[0].package_id == "pkg-A"


def test_list_distribution_records_empty(store):
    assert store.list_distribution_records() == []


# ---------------------------------------------------------------------------
# DMConversationRecord
# ---------------------------------------------------------------------------


def test_save_and_get_dm_conversation(store):
    record = _make_dm_record()
    store.save_dm_conversation(record)

    retrieved = store.get_dm_conversation(record.conv_id)
    assert retrieved is not None
    assert retrieved.conv_id == record.conv_id
    assert retrieved.fsm_state == record.fsm_state
    assert retrieved.trigger_keyword == "link"


def test_get_dm_conversation_not_found(store):
    assert store.get_dm_conversation("nonexistent") is None


def test_upsert_dm_conversation(store):
    record = _make_dm_record()
    store.save_dm_conversation(record)

    advanced = record.model_copy(update={"fsm_state": DMState.SENT, "reply_id": "reply-001"})
    store.save_dm_conversation(advanced)

    retrieved = store.get_dm_conversation(record.conv_id)
    assert retrieved.fsm_state == DMState.SENT
    assert retrieved.reply_id == "reply-001"


def test_list_dm_conversations_by_state(store):
    store.save_dm_conversation(_make_dm_record(state=DMState.REPLY_PLANNED))
    store.save_dm_conversation(_make_dm_record(state=DMState.SENT))

    results = store.list_dm_conversations(fsm_state="reply_planned")
    assert len(results) == 1
    assert results[0].fsm_state == DMState.REPLY_PLANNED


def test_list_dm_conversations_by_user(store):
    store.save_dm_conversation(_make_dm_record(user_id="alice"))
    store.save_dm_conversation(_make_dm_record(user_id="bob"))

    results = store.list_dm_conversations(user_id="alice")
    assert len(results) == 1
    assert results[0].user_id == "alice"
