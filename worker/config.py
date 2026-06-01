"""Worker configuration via pydantic-settings."""

from pathlib import Path
from typing import ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    """Configuration for the Briefer worker."""

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    LLM_API_URL: str = "http://faex:8080/v1"
    LLM_MODEL_NAME: str = "qwen3.6-a3b-mtp:35b"
    WHISPER_MODEL: str = "large-v3"
    DATA_DIR: str = "/data"
    TZ: str = "Europe/Moscow"
    LOG_LEVEL: str = "INFO"
    HEALTH_PORT: int = 8082
    MAX_TASK_DURATION: int = 900
    MAX_RETRIES: int = 3
    MATRIX_HOMESERVER: str = ""
    MATRIX_USER: str = ""
    MATRIX_ACCESS_TOKEN: str = ""
    MATRIX_ROOM_ID: str = ""

    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    VALID_WHISPER_MODELS: ClassVar[set[str]] = {"tiny", "base", "small", "medium", "large-v3"}

    @field_validator("LLM_API_URL")
    @classmethod
    def validate_llm_api_url(cls, v: str) -> str:
        if not v:
            raise ValueError("LLM_API_URL is required")
        if not v.endswith("/v1"):
            v = v.rstrip("/") + "/v1"
        return v

    @field_validator("WHISPER_MODEL")
    @classmethod
    def validate_whisper_model(cls, v: str) -> str:
        if v not in cls.VALID_WHISPER_MODELS:
            raise ValueError(f"WHISPER_MODEL must be one of {cls.VALID_WHISPER_MODELS}")
        return v

    @field_validator("MAX_TASK_DURATION")
    @classmethod
    def validate_max_task_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("MAX_TASK_DURATION must be > 0")
        return v

    @field_validator("MAX_RETRIES")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("MAX_RETRIES must be >= 0")
        return v

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    @property
    def data_dir_path(self) -> Path:
        return Path(self.DATA_DIR)

    @property
    def whisper_model_size(self) -> str:
        parts = self.WHISPER_MODEL.rsplit("-", 1)
        return parts[0] if len(parts) > 1 else self.WHISPER_MODEL
