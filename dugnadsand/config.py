"""Configuration management using pydantic-settings.

All env vars use the DUGNADSAND_ prefix and are loaded from /etc/svend/sites/dugnadsand.env.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """dugnadsand application settings."""

    model_config = SettingsConfigDict(
        env_prefix="DUGNADSAND_",
        env_file="/etc/svend/sites/dugnadsand.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = False
    secret_key: str = ""

    # Database (optional — leave empty for sqlite)
    database_url: str = Field(default="", description="App connection string")

    # Hosts
    allowed_hosts: str = "localhost,127.0.0.1"

    def get_allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
