from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from browser_runtime.audit import get_audit

from .contracts import (
    CommentCategory,
    ConversionEvent,
    DMConversationRecord,
    DMState,
    IdentityMatrix,
    Platform,
    TriagedComment,
)
from .reply_generator import ReplyGeneratorInterface


class FollowerCheckFn(Protocol):
    """Callable that checks whether a user is a follower. Return None if unknown."""

    def __call__(self, platform: Platform, user_id: str) -> bool | None: ...


class DMTriggerFSM:
    """
    States: IDLE → TRIGGER_DETECTED → FOLLOWER_CHECK → REPLY_PLANNED / DM_PLANNED → SENT → CONVERTED
    Also: any state → REJECTED (spam/error)

    Transition rules:
    - IDLE + trigger comment → TRIGGER_DETECTED
    - TRIGGER_DETECTED + follower_check called → FOLLOWER_CHECK
    - FOLLOWER_CHECK + is_follower=True → DM_PLANNED (send DM directly)
    - FOLLOWER_CHECK + is_follower=False/None → REPLY_PLANNED (public reply with DM invite)
    - REPLY_PLANNED / DM_PLANNED + executor result success → SENT
    - SENT + conversion_event recorded → CONVERTED
    - TRIGGER_DETECTED + category=SPAMMY → REJECTED
    """

    def __init__(
        self,
        identity: IdentityMatrix,
        reply_generator: ReplyGeneratorInterface,
        follower_check: FollowerCheckFn | None = None,
    ) -> None:
        self._identity = identity
        self._reply_generator = reply_generator
        self._follower_check = follower_check

    def process_comment(
        self,
        triaged: TriagedComment,
        dry_run: bool = True,
    ) -> DMConversationRecord:
        record = DMConversationRecord(
            platform=triaged.platform,
            post_id=triaged.post_id,
            comment_id=triaged.comment_id,
            user_id=triaged.user_id,
            comment_text=triaged.text,
            comment_category=triaged.category,
            trigger_keyword=triaged.detected_trigger,
            fsm_state=DMState.IDLE,
            dry_run=dry_run,
        )

        if triaged.category == CommentCategory.SPAMMY:
            record = self._advance_state(record, DMState.REJECTED)
            get_audit().log(
                "dm_fsm.rejected",
                {"conv_id": record.conv_id, "reason": "spammy"},
                level="WARNING",
            )
            return record

        record = self._advance_state(record, DMState.TRIGGER_DETECTED)

        is_follower: bool | None = None
        if self._follower_check is not None:
            is_follower = self._follower_check(triaged.platform, triaged.user_id)
            record = self._advance_state(
                record.model_copy(update={"is_follower": is_follower}),
                DMState.FOLLOWER_CHECK,
            )

        reply_text = self._reply_generator.generate_reply(triaged, self._identity)

        if is_follower is True:
            dm_text = self._identity.comment_style.dm_offer_template
            record = self._advance_state(
                record.model_copy(update={"dm_text": dm_text, "reply_text": reply_text}),
                DMState.DM_PLANNED,
            )
        else:
            record = self._advance_state(
                record.model_copy(update={"reply_text": reply_text}),
                DMState.REPLY_PLANNED,
            )

        get_audit().log(
            "dm_fsm.planned",
            {
                "conv_id": record.conv_id,
                "state": record.fsm_state,
                "platform": triaged.platform,
                "dry_run": dry_run,
            },
        )
        return record

    def record_sent(
        self,
        record: DMConversationRecord,
        reply_id: str | None = None,
        dm_message_id: str | None = None,
    ) -> DMConversationRecord:
        updated = record.model_copy(
            update={
                "reply_id": reply_id,
                "dm_message_id": dm_message_id,
            }
        )
        result = self._advance_state(updated, DMState.SENT)
        get_audit().log("dm_fsm.sent", {"conv_id": result.conv_id, "reply_id": reply_id})
        return result

    def record_conversion(
        self,
        record: DMConversationRecord,
        event: ConversionEvent,
    ) -> DMConversationRecord:
        events = list(record.conversion_events) + [event]
        updated = record.model_copy(update={"conversion_events": events})
        result = self._advance_state(updated, DMState.CONVERTED)
        get_audit().log(
            "dm_fsm.converted",
            {
                "conv_id": result.conv_id,
                "event_type": event.event_type,
                "value_usd": event.value_usd,
            },
        )
        return result

    def _advance_state(
        self,
        record: DMConversationRecord,
        new_state: DMState,
    ) -> DMConversationRecord:
        get_audit().log(
            "dm_fsm.transition",
            {
                "conv_id": record.conv_id,
                "from": record.fsm_state,
                "to": new_state,
            },
        )
        return record.model_copy(
            update={
                "fsm_state": new_state,
                "updated_at": datetime.now(UTC),
            }
        )
