"""
Typed request/response objects for all browser_runtime consumers.

Stage code should import from here — never from provider/adapter internals.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Platform(StrEnum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    SHOPIFY = "shopify"
    ANALYTICS = "analytics"


class ProviderType(StrEnum):
    BROWSER_USE = "browser_use"
    CODE_AGENT = "code_agent"
    SKILL_API = "skill_api"
    PLATFORM_API = "platform_api"
    MOCK = "mock"


class ActionType(StrEnum):
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    EXTRACT = "extract"
    NAVIGATE = "navigate"
    SUBMIT = "submit"


# ---------------------------------------------------------------------------
# Session types
# ---------------------------------------------------------------------------


class SessionState(BaseModel):
    """Serialisable snapshot of a browser session (cookies, storage)."""

    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    platform: Platform | None = None
    cookies: dict[str, Any] = {}
    local_storage: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class TabInfo(BaseModel):
    tab_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str = ""
    title: str = ""
    is_active: bool = False


# ---------------------------------------------------------------------------
# Low-level browser action types
# ---------------------------------------------------------------------------


class BrowserAction(BaseModel):
    action_type: ActionType
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    timeout_ms: int = 5000
    metadata: dict[str, Any] = {}


class ActionResult(BaseModel):
    success: bool
    action_type: ActionType
    duration_ms: float = 0.0
    data: dict[str, Any] = {}
    error: str | None = None
    screenshot_b64: str | None = None  # base64 PNG, if captured


# ---------------------------------------------------------------------------
# Provider request/response types
# ---------------------------------------------------------------------------


class AgentTask(BaseModel):
    """High-level task handed to a BrowserUse / agent provider."""

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    url: str | None = None
    actions: list[BrowserAction] = []
    max_steps: int = 20
    timeout_seconds: int = 120
    dry_run: bool = False
    metadata: dict[str, Any] = {}


class AgentResult(BaseModel):
    task_id: str
    success: bool
    provider: ProviderType
    duration_seconds: float = 0.0
    steps_taken: int = 0
    output: dict[str, Any] = {}
    artifacts: list[str] = []  # local file paths to downloaded assets
    error: str | None = None
    dry_run: bool = False


class ExtractionSchema(BaseModel):
    """Describes what to pull out during bulk extraction."""

    fields: dict[str, str]  # field_name -> natural-language hint
    pagination: bool = False
    max_pages: int = 1


class ExtractionResult(BaseModel):
    url: str
    success: bool
    data: dict[str, Any] = {}
    error: str | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SkillRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str
    params: dict[str, Any] = {}
    timeout_seconds: int = 30
    dry_run: bool = False


class SkillResult(BaseModel):
    request_id: str
    skill_name: str
    success: bool
    result: dict[str, Any] = {}
    error: str | None = None
    duration_seconds: float = 0.0


class PlatformAPIRequest(BaseModel):
    """Request routed through an official platform REST/GraphQL API."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
    endpoint: str
    params: dict[str, Any] = {}
    body: dict[str, Any] = {}
    dry_run: bool = False


class PlatformAPIResponse(BaseModel):
    request_id: str
    platform: Platform
    status_code: int = 200
    data: dict[str, Any] = {}
    error: str | None = None
    duration_ms: float = 0.0
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Platform adapter request/response types
# (Stage consumers use these — not raw BrowserActions)
# ---------------------------------------------------------------------------


class PostContentRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform
    caption: str
    hashtags: list[str] = []
    media_path: str | None = None   # local filesystem path
    media_url: str | None = None    # remote URL (alternative to media_path)
    scheduled_at: datetime | None = None
    dry_run: bool = False
    ai_disclosure: bool = True      # must stay True per operating rules


class PostContentResult(BaseModel):
    request_id: str
    platform: Platform
    success: bool
    post_id: str | None = None
    post_url: str | None = None
    posted_at: datetime | None = None
    error: str | None = None
    dry_run: bool = False


class CommentReplyRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform
    post_id: str
    comment_id: str
    reply_text: str
    dry_run: bool = False


class CommentReplyResult(BaseModel):
    request_id: str
    platform: Platform
    success: bool
    reply_id: str | None = None
    error: str | None = None
    dry_run: bool = False


class DMRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform
    recipient_id: str
    message: str
    ai_disclosure: bool = True  # must stay True per operating rules
    dry_run: bool = False


class DMResult(BaseModel):
    request_id: str
    platform: Platform
    success: bool
    message_id: str | None = None
    error: str | None = None
    dry_run: bool = False


class AnalyticsFetchRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform
    post_id: str | None = None
    account_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None


class AnalyticsData(BaseModel):
    request_id: str
    platform: Platform
    post_id: str | None = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    follows_gained: int = 0
    watch_time_avg_seconds: float = 0.0
    completion_rate_pct: float = 0.0
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TrendingFetchRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform
    niche_tags: list[str] = []
    limit: int = 20


class TrendingItem(BaseModel):
    platform: Platform
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    audio_title: str | None = None
    audio_author: str | None = None
    audio_url: str | None = None
    usage_count: int = 0
    growth_rate_pct: float = 0.0
    niche_tags: list[str] = []
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
