from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PIPELINE_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite:///./pipeline.db",
        description="SQLite URL or future Postgres DSN",
    )
    dry_run: bool = Field(default=False, description="Skip external I/O and artifact writes")
    feature_stage5_enabled: bool = Field(
        default=False,
        description="Stage 5 monetization features (off for main demo)",
    )
    artifacts_dir: Path = Field(
        default=Path("./artifacts"),
        description="Local directory for generated media",
    )
    disclosure_demo: bool = Field(
        default=True,
        description="Mark outputs as AI/sandbox disclosure-aware demo",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
