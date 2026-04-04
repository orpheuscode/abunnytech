"""
Stage 3: Distribute & Engage

Consumes ContentPackage objects and emits DistributionRecord + DMConversationRecord objects.

Public surface:
    PostingScheduler    — priority queue for scheduled posts
    PostingExecutor     — executes posts via a PlatformAdapter
    CommentTriageEngine — classifies incoming comments
    MockReplyGenerator  — persona-consistent reply generation (offline/mock)
    DMTriggerFSM        — finite-state machine for DM trigger flows
    StoryPlanner        — generates 3-slide story engagement plans
    Stage3Store         — SQLite persistence for output records
"""
from .comment_triage import CommentTriageEngine
from .contracts import (
    CommentCategory,
    CommentStyle,
    ContentPackage,
    ConversionEvent,
    DistributionRecord,
    DistributionStatus,
    DMConversationRecord,
    DMState,
    IdentityMatrix,
    Platform,
    StoryEngagementPlan,
    StorySlide,
    TriagedComment,
)
from .dm_fsm import DMTriggerFSM, FollowerCheckFn
from .executor import PostingExecutor
from .persistence import Stage3Store
from .reply_generator import MockReplyGenerator, ReplyGeneratorInterface
from .scheduler import PlatformTarget, PostingScheduler, PostingWindow, ScheduledPost
from .story_planner import StoryPlanner

__all__ = [
    # Contracts
    "CommentCategory",
    "CommentStyle",
    "ContentPackage",
    "ConversionEvent",
    "DMConversationRecord",
    "DMState",
    "DistributionRecord",
    "DistributionStatus",
    "IdentityMatrix",
    "Platform",
    "StoryEngagementPlan",
    "StorySlide",
    "TriagedComment",
    # Scheduler
    "PlatformTarget",
    "PostingScheduler",
    "PostingWindow",
    "ScheduledPost",
    # Executor
    "PostingExecutor",
    # Triage
    "CommentTriageEngine",
    # Reply generation
    "MockReplyGenerator",
    "ReplyGeneratorInterface",
    # DM FSM
    "DMTriggerFSM",
    "FollowerCheckFn",
    # Story
    "StoryPlanner",
    # Persistence
    "Stage3Store",
]
