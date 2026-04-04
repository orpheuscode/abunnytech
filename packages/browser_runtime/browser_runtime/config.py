"""
Runtime configuration: rate limits, retry policies, kill switches, settings.

All values have safe defaults (dry_run=True, provider=mock).
Override via environment variables prefixed with BROWSER_ or via .env file.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RateLimitConfig(BaseModel):
    requests_per_minute: int = 10
    requests_per_hour: int = 100
    requests_per_day: int = 500
    burst_allowance: int = 3  # extra requests allowed before throttling


class RetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 60.0
    jitter: bool = True
    # Exception class names (strings) that are considered retryable
    retryable_on: list[str] = ["httpx.TransportError", "TimeoutError", "ConnectionError"]


class KillSwitchConfig(BaseModel):
    """Global or per-platform emergency stop. Raises KillSwitchTriggered immediately."""

    enabled: bool = False
    reason: str = "Kill switch activated — no reason provided."


class PlatformConfig(BaseModel):
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    kill_switch: KillSwitchConfig = Field(default_factory=KillSwitchConfig)
    api_base_url: str | None = None
    # Name of the env var that holds the credential (token/cookie/key).
    # The runtime reads it at call time so secrets are never stored in config objects.
    credentials_env_key: str | None = None


class BrowserRuntimeSettings(BaseSettings):
    """
    Top-level settings loaded from environment / .env file.

    Safe defaults: dry_run=True, provider=mock.
    Set BROWSER_DRY_RUN=false and BROWSER_PROVIDER=browser_use to go live.
    """

    dry_run: bool = True
    log_level: str = "INFO"
    audit_log_path: str = "./logs/browser_runtime_audit.jsonl"
    # Which provider to use: mock | browser_use | code_agent | skill_api | platform_api
    provider: str = "mock"

    # Per-platform config (env vars: BROWSER_INSTAGRAM__RATE_LIMIT__REQUESTS_PER_MINUTE=5)
    instagram: PlatformConfig = Field(default_factory=PlatformConfig)
    tiktok: PlatformConfig = Field(default_factory=PlatformConfig)
    shopify: PlatformConfig = Field(default_factory=PlatformConfig)
    analytics: PlatformConfig = Field(default_factory=PlatformConfig)

    # Global kill switch — overrides all platform-level switches
    global_kill_switch: KillSwitchConfig = Field(default_factory=KillSwitchConfig)

    model_config = SettingsConfigDict(
        env_prefix="BROWSER_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def platform_config(self, platform: str) -> PlatformConfig:
        """Return the PlatformConfig for the given platform name string."""
        return getattr(self, platform.lower(), PlatformConfig())


# Module-level singleton — stages can import this directly.
# Tests should override by constructing a fresh BrowserRuntimeSettings() with test values.
_settings: BrowserRuntimeSettings | None = None


def get_settings() -> BrowserRuntimeSettings:
    global _settings
    if _settings is None:
        _settings = BrowserRuntimeSettings()
    return _settings


def override_settings(settings: BrowserRuntimeSettings) -> None:
    """Replace the singleton — intended for tests only."""
    global _settings
    _settings = settings
