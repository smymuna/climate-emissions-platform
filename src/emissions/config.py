from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration from ``EMISSIONS_*`` environment variables (or ``.env``)."""

    model_config = SettingsConfigDict(env_prefix="EMISSIONS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://emissions:emissions@localhost:5432/emissions"
    landing_dir: Path = Path("data/landing")
    http_timeout_s: float = Field(default=60.0, gt=0)
    http_retries: int = Field(default=3, ge=0, le=10)
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]
    """Browser origins allowed to call the API, e.g. the deployed frontend."""
    cors_origin_regex: str | None = None
    """Optional regex for extra origins, e.g. Vercel preview deployments."""
