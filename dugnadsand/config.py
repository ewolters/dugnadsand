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

    # Fernet key for the application-ingress fields. Comma-separated to
    # rotate: new key first, re-seal, then drop the old one. Empty means the
    # encrypted fields cannot be read or written, which fails loudly rather
    # than silently storing plaintext.
    field_encryption_key: str = ""

    # The legal person the terms run to. Section 1 tells a joining organization
    # the network "is operated by the entity named at the foot of this page",
    # and sections 4 and 5 hand that entity an indemnity and a limitation of
    # liability — so if the foot of the page names nobody, an organization has
    # agreed to indemnify a party it cannot identify.
    #
    # It lives here, once, because entity separation is expected to change it
    # (see docs/for-counsel.md §7) and the change should be a value rather than
    # a hunt through templates. Empty renders nothing at all: a page silent
    # about the operator is better than one naming the wrong one.
    operator_legal_name: str = "SVEND, LLC"

    # Hosts
    allowed_hosts: str = "localhost,127.0.0.1"

    def get_allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
