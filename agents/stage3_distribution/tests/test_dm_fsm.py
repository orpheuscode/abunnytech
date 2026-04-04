"""Tests for DMTriggerFSM."""
from __future__ import annotations

import pytest
from browser_runtime.audit import AuditLogger, override_audit

from ..contracts import (
    CommentCategory,
    ConversionEvent,
    DMState,
    Platform,
    TriagedComment,
)
from ..dm_fsm import DMTriggerFSM
from ..reply_generator import MockReplyGenerator
from .fixtures import make_identity


@pytest.fixture(autouse=True)
def silence_audit(tmp_path):
    override_audit(AuditLogger(str(tmp_path / "audit.jsonl")))


@pytest.fixture
def identity():
    return make_identity()


@pytest.fixture
def generator():
    return MockReplyGenerator()


@pytest.fixture
def fsm(identity, generator):
    return DMTriggerFSM(identity=identity, reply_generator=generator)


def _trigger_comment(
    category: CommentCategory = CommentCategory.TRIGGER_DM,
    text: str = "where is the link?",
) -> TriagedComment:
    return TriagedComment(
        comment_id="c1",
        platform=Platform.TIKTOK,
        post_id="p1",
        user_id="u1",
        text=text,
        category=category,
        detected_trigger="link" if category == CommentCategory.TRIGGER_DM else None,
        reply_priority=1,
    )


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def test_spammy_comment_goes_to_rejected(fsm):
    triaged = _trigger_comment(category=CommentCategory.SPAMMY, text="SCAM SCAM")
    record = fsm.process_comment(triaged)
    assert record.fsm_state == DMState.REJECTED
    assert record.reply_text is None
    assert record.dm_text is None


def test_trigger_without_follower_check_lands_on_reply_planned(fsm):
    triaged = _trigger_comment()
    record = fsm.process_comment(triaged)
    assert record.fsm_state == DMState.REPLY_PLANNED
    assert record.reply_text is not None
    assert record.dm_text is None


def test_trigger_with_follower_true_lands_on_dm_planned(identity, generator):
    fsm = DMTriggerFSM(
        identity=identity,
        reply_generator=generator,
        follower_check=lambda platform, user_id: True,
    )
    triaged = _trigger_comment()
    record = fsm.process_comment(triaged)
    assert record.fsm_state == DMState.DM_PLANNED
    assert record.dm_text is not None
    assert record.is_follower is True


def test_trigger_with_follower_false_lands_on_reply_planned(identity, generator):
    fsm = DMTriggerFSM(
        identity=identity,
        reply_generator=generator,
        follower_check=lambda platform, user_id: False,
    )
    triaged = _trigger_comment()
    record = fsm.process_comment(triaged)
    assert record.fsm_state == DMState.REPLY_PLANNED
    assert record.is_follower is False


def test_record_sent_advances_to_sent(fsm):
    triaged = _trigger_comment()
    record = fsm.process_comment(triaged)
    sent = fsm.record_sent(record, reply_id="reply-001")
    assert sent.fsm_state == DMState.SENT
    assert sent.reply_id == "reply-001"


def test_record_conversion_advances_to_converted(fsm):
    triaged = _trigger_comment()
    record = fsm.process_comment(triaged)
    sent = fsm.record_sent(record, reply_id="reply-001")
    event = ConversionEvent(event_type="link_clicked", value_usd=0.0)
    converted = fsm.record_conversion(sent, event)
    assert converted.fsm_state == DMState.CONVERTED
    assert len(converted.conversion_events) == 1


def test_multiple_conversions_accumulate(fsm):
    triaged = _trigger_comment()
    record = fsm.process_comment(triaged)
    sent = fsm.record_sent(record)
    e1 = ConversionEvent(event_type="link_clicked")
    e2 = ConversionEvent(event_type="purchase", value_usd=29.99)
    c1 = fsm.record_conversion(sent, e1)
    c2 = fsm.record_conversion(c1, e2)
    assert len(c2.conversion_events) == 2
    assert c2.conversion_events[1].value_usd == 29.99


def test_fsm_is_immutable_original_unchanged(fsm):
    triaged = _trigger_comment()
    record = fsm.process_comment(triaged)
    original_state = record.fsm_state
    fsm.record_sent(record)  # returns new record, doesn't mutate record
    assert record.fsm_state == original_state


def test_dm_trigger_populates_trigger_keyword(fsm):
    triaged = _trigger_comment()
    record = fsm.process_comment(triaged)
    assert record.trigger_keyword == "link"


def test_non_trigger_comment_still_planned(fsm):
    """PRAISE comments should also get REPLY_PLANNED (generic reply flow)."""
    triaged = _trigger_comment(category=CommentCategory.PRAISE, text="I love this so much!")
    record = fsm.process_comment(triaged)
    assert record.fsm_state == DMState.REPLY_PLANNED
