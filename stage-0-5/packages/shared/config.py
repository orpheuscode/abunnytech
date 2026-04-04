"""Global configuration via pydantic-settings. Single source of truth for env vars."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # AI Providers
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""

    # Social Platforms (sandbox/test accounts)
    tiktok_session_id: str = ""
    instagram_session_id: str = ""
    youtube_api_key: str = ""

    # Feature Flags
    feature_stage5_monetize: bool = False
    dry_run: bool = True

    # Database
    database_url: str = "sqlite+aiosqlite:///./abunnytech.db"

    # Control Plane
    control_plane_host: str = "0.0.0.0"
    control_plane_port: int = 8000

    # Dashboard
    dashboard_port: int = 8501


@lru_cache
def get_settings() -> Settings:
    return Settings()
