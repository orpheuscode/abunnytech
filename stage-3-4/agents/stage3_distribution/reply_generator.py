from __future__ import annotations

import random
from abc import ABC, abstractmethod

from .contracts import CommentCategory, IdentityMatrix, TriagedComment


class ReplyGeneratorInterface(ABC):
    @abstractmethod
    def generate_reply(self, comment: TriagedComment, identity: IdentityMatrix) -> str:
        """Generate a persona-consistent reply for the given comment."""


class MockReplyGenerator(ReplyGeneratorInterface):
    """
    Template-based reply generator. No external LLM needed — works fully offline.

    Selects from templates in identity.comment_style based on comment category.
    Falls back to sensible defaults if templates are empty.
    """

    def __init__(self, _random: bool = False) -> None:
        self._random = _random

    def generate_reply(self, comment: TriagedComment, identity: IdentityMatrix) -> str:
        style = identity.comment_style
        name = identity.persona_name

        match comment.category:
            case CommentCategory.TRIGGER_DM:
                template = style.dm_offer_template or "Hey! DM me for the link 🐰"
                return template

            case CommentCategory.SPAMMY:
                return ""

            case CommentCategory.QUESTION:
                base = self._pick_template(
                    style.question_reply_templates,
                    "Great question! {answer}",
                )
                return base.format(answer="check my bio for more info!")

            case CommentCategory.PRAISE:
                return self._pick_template(
                    style.positive_reply_templates,
                    f"Thank you so much! 🥰 — {name}",
                )

            case CommentCategory.COMPLAINT:
                return (
                    f"I'm sorry to hear that! DM me and I'll make it right 🐰 — {name}"
                )

            case CommentCategory.ENGAGING | _:
                return self._pick_template(
                    style.positive_reply_templates,
                    f"Thanks for the love! 💕 — {name}",
                )

    def _pick_template(self, templates: list[str], fallback: str) -> str:
        if not templates:
            return fallback
        if self._random:
            return random.choice(templates)
        return templates[0]
