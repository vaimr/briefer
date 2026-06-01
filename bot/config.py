"""Bot configuration via pydantic-settings."""

import re
from typing import ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotConfig(BaseSettings):
    """Configuration for the Briefer Matrix bot."""

    MATRIX_HOMESERVER: str = ""
    MATRIX_USER: str = ""
    MATRIX_PASSWORD: str = ""
    MATRIX_ACCESS_TOKEN: str = ""
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    LOG_LEVEL: str = "INFO"
    HEALTH_PORT: int = 8081
    HELP_TEXT_FILE: str = "/etc/briefer/help.txt"
    TZ: str = "Europe/Moscow"

    _VALID_LOG_LEVELS: ClassVar[set[str]] = {
        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL",
    }

    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("MATRIX_HOMESERVER")
    @classmethod
    def validate_homeserver(cls, v: str) -> str:
        """Allow empty (checked at runtime). Normalize non-empty values."""
        if not v:
            return v
        if not v.startswith(("http://", "https://")):
            v = f"https://{v}"
        if v.endswith("/"):
            v = v.rstrip("/")
        return v

    @field_validator("MATRIX_USER")
    @classmethod
    def validate_matrix_user(cls, v: str) -> str:
        """Allow empty (checked at runtime). Validate format if non-empty."""
        if not v:
            return v
        if not v.startswith("@"):
            raise ValueError("MATRIX_USER must start with @")
        return v

    @field_validator("REDIS_PORT")
    @classmethod
    def validate_redis_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("REDIS_PORT must be between 1 and 65535")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        if v.upper() not in cls._VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {cls._VALID_LOG_LEVELS}")
        return v.upper()

    def validate_required(self) -> None:
        """Raise if required Matrix fields are empty. Call before connecting."""
        if not self.MATRIX_HOMESERVER:
            raise ValueError("MATRIX_HOMESERVER is required")
        if not self.MATRIX_USER:
            raise ValueError("MATRIX_USER is required")

    @property
    def matrix_client_config(self) -> dict:
        return {
            "homeserver_url": self.MATRIX_HOMESERVER,
            "user": self.MATRIX_USER,
            "password": self.MATRIX_PASSWORD,
            "device_name": f"briefer-bot-{self.TZ}",
        }

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    @property
    def matrix_user_display_name(self) -> str:
        match = re.match(r"^@([^:]+)", self.MATRIX_USER)
        return match.group(1) if match else self.MATRIX_USER
