"""Tests for CommentTriageEngine and MockReplyGenerator."""
from __future__ import annotations

import pytest
from browser_runtime.audit import AuditLogger, override_audit

from ..comment_triage import CommentTriageEngine
from ..contracts import CommentCategory, Platform
from ..reply_generator import MockReplyGenerator
from .fixtures import make_identity


@pytest.fixture(autouse=True)
def silence_audit(tmp_path):
    override_audit(AuditLogger(str(tmp_path / "audit.jsonl")))


@pytest.fixture
def identity():
    return make_identity()


@pytest.fixture
def engine(identity):
    return CommentTriageEngine(identity=identity)


@pytest.fixture
def generator():
    return MockReplyGenerator()


# ---------------------------------------------------------------------------
# CommentTriageEngine
# ---------------------------------------------------------------------------


def _triage(engine: CommentTriageEngine, text: str) -> CommentCategory:
    result = engine.triage(
        comment_id="c1",
        platform=Platform.TIKTOK,
        post_id="p1",
        user_id="u1",
        text=text,
    )
    return result.category


def test_trigger_keyword_detected(engine):
    assert _triage(engine, "where can I buy this?") == CommentCategory.TRIGGER_DM


def test_trigger_keyword_case_insensitive(engine):
    assert _triage(engine, "WHERE IS THE LINK??") == CommentCategory.TRIGGER_DM


def test_trigger_wins_over_question(engine):
    # "how" is in trigger_keywords and is also a question word — TRIGGER_DM should win
    result = engine.triage("c1", Platform.TIKTOK, "p1", "u1", "how do I get this?")
    assert result.category == CommentCategory.TRIGGER_DM
    assert result.detected_trigger == "how"


def test_spam_detection_all_caps(engine):
    assert _triage(engine, "SCAM SCAM SCAM THIS IS FAKE GARBAGE") == CommentCategory.SPAMMY


def test_spam_detection_repeating_chars(engine):
    assert _triage(engine, "loooooooooool this is sooo goood") == CommentCategory.SPAMMY


def test_question_detected(engine):
    assert _triage(engine, "Is this available in my size?") == CommentCategory.QUESTION


def test_complaint_detected(engine):
    assert _triage(engine, "honestly this looks terrible and awful") == CommentCategory.COMPLAINT


def test_praise_detected(engine):
    result = _triage(engine, "this is so gorgeous and beautiful omg love it")
    assert result == CommentCategory.PRAISE


def test_default_engaging(engine):
    assert _triage(engine, "ok") == CommentCategory.ENGAGING


def test_triage_batch_sorted_by_priority(engine):
    comments = [
        {"comment_id": "c1", "platform": Platform.TIKTOK, "post_id": "p1", "user_id": "u1",
         "text": "gorgeous!"},
        {"comment_id": "c2", "platform": Platform.TIKTOK, "post_id": "p1", "user_id": "u2",
         "text": "where can I buy this?"},
        {"comment_id": "c3", "platform": Platform.TIKTOK, "post_id": "p1", "user_id": "u3",
         "text": "SCAM SCAM SCAM FAKE"},
    ]
    results = engine.triage_batch(comments)
    priorities = [r.reply_priority for r in results]
    assert priorities == sorted(priorities)


def test_sentiment_positive(engine):
    result = engine.triage("c1", Platform.TIKTOK, "p1", "u1", "I love this amazing gorgeous look")
    assert result.sentiment_score > 0


def test_sentiment_negative(engine):
    result = engine.triage("c1", Platform.TIKTOK, "p1", "u1", "terrible awful scam fake trash")
    assert result.sentiment_score < 0


# ---------------------------------------------------------------------------
# MockReplyGenerator
# ---------------------------------------------------------------------------


def test_reply_generator_trigger_dm(generator, identity):
    from ..contracts import TriagedComment
    triaged = TriagedComment(
        comment_id="c1", platform=Platform.TIKTOK, post_id="p1", user_id="u1",
        text="where is the link?", category=CommentCategory.TRIGGER_DM,
        detected_trigger="link",
    )
    reply = generator.generate_reply(triaged, identity)
    assert "DM" in reply or "dm" in reply.lower()


def test_reply_generator_spammy_returns_empty(generator, identity):
    from ..contracts import TriagedComment
    triaged = TriagedComment(
        comment_id="c1", platform=Platform.TIKTOK, post_id="p1", user_id="u1",
        text="SCAM SCAM", category=CommentCategory.SPAMMY,
    )
    reply = generator.generate_reply(triaged, identity)
    assert reply == ""


def test_reply_generator_question_fills_answer(generator, identity):
    from ..contracts import TriagedComment
    triaged = TriagedComment(
        comment_id="c1", platform=Platform.TIKTOK, post_id="p1", user_id="u1",
        text="Is this real?", category=CommentCategory.QUESTION,
    )
    reply = generator.generate_reply(triaged, identity)
    assert "{answer}" not in reply  # template placeholder must be filled


def test_reply_generator_praise(generator, identity):
    from ..contracts import TriagedComment
    triaged = TriagedComment(
        comment_id="c1", platform=Platform.TIKTOK, post_id="p1", user_id="u1",
        text="gorgeous!", category=CommentCategory.PRAISE,
    )
    reply = generator.generate_reply(triaged, identity)
    assert len(reply) > 0


def test_reply_generator_complaint(generator, identity):
    from ..contracts import TriagedComment
    triaged = TriagedComment(
        comment_id="c1", platform=Platform.TIKTOK, post_id="p1", user_id="u1",
        text="this is terrible", category=CommentCategory.COMPLAINT,
    )
    reply = generator.generate_reply(triaged, identity)
    assert len(reply) > 0
