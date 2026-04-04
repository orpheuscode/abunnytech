from __future__ import annotations

import re

from browser_runtime.audit import get_audit

from .contracts import CommentCategory, IdentityMatrix, Platform, TriagedComment

POSITIVE_WORDS = {
    "love", "amazing", "great", "awesome", "beautiful", "perfect", "cute",
    "obsessed", "need", "want", "gorgeous", "stunning", "wow", "yes", "omg",
}
NEGATIVE_WORDS = {
    "hate", "ugly", "terrible", "awful", "bad", "worst", "scam", "fake",
    "disappointed", "trash", "boring", "overpriced", "skip", "no",
}
QUESTION_WORDS = {
    "what", "where", "when", "why", "how", "who", "which", "is", "are",
    "can", "could", "would", "should", "do", "does", "did",
}


class CommentTriageEngine:
    def __init__(self, identity: IdentityMatrix) -> None:
        self._identity = identity

    def triage(
        self,
        comment_id: str,
        platform: Platform,
        post_id: str,
        user_id: str,
        text: str,
    ) -> TriagedComment:
        trigger = self._detect_trigger(text)
        if trigger:
            return TriagedComment(
                comment_id=comment_id,
                platform=platform,
                post_id=post_id,
                user_id=user_id,
                text=text,
                category=CommentCategory.TRIGGER_DM,
                reply_priority=1,
                detected_trigger=trigger,
                sentiment_score=self._sentiment_score(text),
            )

        if self._is_spam(text):
            return TriagedComment(
                comment_id=comment_id,
                platform=platform,
                post_id=post_id,
                user_id=user_id,
                text=text,
                category=CommentCategory.SPAMMY,
                reply_priority=10,
                sentiment_score=self._sentiment_score(text),
            )

        words = text.lower().split()
        first_word = words[0] if words else ""

        if text.strip().endswith("?") or first_word in QUESTION_WORDS:
            return TriagedComment(
                comment_id=comment_id,
                platform=platform,
                post_id=post_id,
                user_id=user_id,
                text=text,
                category=CommentCategory.QUESTION,
                reply_priority=2,
                sentiment_score=self._sentiment_score(text),
            )

        score = self._sentiment_score(text)

        if score < -0.1:
            return TriagedComment(
                comment_id=comment_id,
                platform=platform,
                post_id=post_id,
                user_id=user_id,
                text=text,
                category=CommentCategory.COMPLAINT,
                reply_priority=3,
                sentiment_score=score,
            )

        if score > 0.1:
            return TriagedComment(
                comment_id=comment_id,
                platform=platform,
                post_id=post_id,
                user_id=user_id,
                text=text,
                category=CommentCategory.PRAISE,
                reply_priority=4,
                sentiment_score=score,
            )

        return TriagedComment(
            comment_id=comment_id,
            platform=platform,
            post_id=post_id,
            user_id=user_id,
            text=text,
            category=CommentCategory.ENGAGING,
            reply_priority=5,
            sentiment_score=score,
        )

    def triage_batch(self, comments: list[dict]) -> list[TriagedComment]:
        results = [
            self.triage(
                comment_id=c["comment_id"],
                platform=c["platform"],
                post_id=c["post_id"],
                user_id=c["user_id"],
                text=c["text"],
            )
            for c in comments
        ]
        get_audit().log("comment_triage.batch", {"count": len(results)})
        return sorted(results, key=lambda t: t.reply_priority)

    def _detect_trigger(self, text: str) -> str | None:
        lowered = text.lower()
        for keyword in self._identity.comment_style.trigger_keywords:
            if keyword.lower() in lowered:
                return keyword
        return None

    def _is_spam(self, text: str) -> bool:
        if not text:
            return False
        alpha_chars = [c for c in text if c.isalpha()]
        if alpha_chars and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.5:
            return True
        if text.lower().count("http") > 3:
            return True
        if re.search(r"(.)\1{4,}", text):
            return True
        return False

    def _sentiment_score(self, text: str) -> float:
        words = re.findall(r"[a-zA-Z]+", text.lower())
        if not words:
            return 0.0
        pos = sum(1 for w in words if w in POSITIVE_WORDS)
        neg = sum(1 for w in words if w in NEGATIVE_WORDS)
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / total
