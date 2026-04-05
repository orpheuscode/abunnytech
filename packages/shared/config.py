"""Global configuration via pydantic-settings. Single source of truth for env vars."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # AI Providers
    browser_use_api_key: str = ""
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    google_api_key: str = ""
    gemini_api_key: str = ""
    twelve_labs_api_key: str = ""
    twelvelabs_api_key: str = ""

    # Social Platforms (sandbox/test accounts)
    tiktok_session_id: str = ""
    instagram_session_id: str = ""
    youtube_api_key: str = ""

    # Feature Flags
    feature_stage5_monetize: bool = False
    dry_run: bool = True

    # Database
    database_url: str = "sqlite+aiosqlite:///./abunnytech.db"
    hackathon_pipeline_db_path: str = "data/hackathon_pipelines.sqlite3"

    # Control Plane
    control_plane_host: str = "0.0.0.0"
    control_plane_port: int = 8000
    hackathon_loop_interval_seconds: float = 300.0
    hackathon_loop_max_cycles: int | None = None
    hackathon_niche_query: str = "dropship"
    hackathon_default_caption: str = "Auto-generated UGC"
    hackathon_product_image_path: str = "data/reference_assets/product_reference.png"
    hackathon_avatar_image_path: str = "data/reference_assets/avatar_reference.png"
    hackathon_media_path: str = "output/hackathon_videos/generated_reel.mp4"
    hackathon_loop_workdir: str = "data/loop_runner"
    browser_use_cdp_url: str = ""
    browser_use_headless: bool = False
    chrome_executable_path: str = ""
    chrome_user_data_dir: str = ""
    chrome_profile_directory: str = ""

    # Dashboard
    dashboard_port: int = 8501

    @field_validator("hackathon_loop_max_cycles", mode="before")
    @classmethod
    def _empty_loop_max_cycles_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
