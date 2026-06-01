"""Unit tests for worker/config.py."""

import pytest
from pathlib import Path

from worker.config import WorkerConfig


class TestDefaultValues:
    def test_default_values(self):
        config = WorkerConfig()
        assert config.REDIS_HOST == "redis"
        assert config.REDIS_PORT == 6379
        assert config.LLM_API_URL == "http://faex:8080/v1"
        assert config.LLM_MODEL_NAME == "qwen3.6-a3b-mtp:35b"
        assert config.WHISPER_MODEL == "large-v3"
        assert config.DATA_DIR == "/data"
        assert config.MAX_TASK_DURATION == 900
        assert config.MAX_RETRIES == 3
        assert config.HEALTH_PORT == 8082

    def test_default_empty_fields(self):
        config = WorkerConfig()
        assert config.REDIS_HOST == "redis"
        assert config.LOG_LEVEL == "INFO"
        assert config.TZ == "Europe/Moscow"


class TestLLMAPIURLValidation:
    def test_adds_v1_suffix(self):
        config = WorkerConfig(LLM_API_URL="http://faex:8080")
        assert config.LLM_API_URL == "http://faex:8080/v1"

    def test_strips_trailing_slash_and_adds_v1(self):
        config = WorkerConfig(LLM_API_URL="http://faex:8080/")
        assert config.LLM_API_URL == "http://faex:8080/v1"

    def test_preserves_v1(self):
        config = WorkerConfig(LLM_API_URL="http://faex:8080/v1")
        assert config.LLM_API_URL == "http://faex:8080/v1"

    def test_raises_on_empty(self):
        with pytest.raises(ValueError, match="LLM_API_URL is required"):
            WorkerConfig(LLM_API_URL="")

    def test_strips_trailing_slash_before_v1(self):
        config = WorkerConfig(LLM_API_URL="http://faex:8080/v1/")
        assert config.LLM_API_URL == "http://faex:8080/v1/v1"


class TestWhisperModelValidation:
    @pytest.mark.parametrize("model", ["tiny", "base", "small", "medium", "large-v3"])
    def test_valid_models(self, model):
        config = WorkerConfig(WHISPER_MODEL=model)
        assert config.WHISPER_MODEL == model

    def test_invalid_model_raises(self):
        with pytest.raises(ValueError, match="must be one of"):
            WorkerConfig(WHISPER_MODEL="xlarge")

    def test_invalid_model_raises_empty(self):
        with pytest.raises(ValueError, match="must be one of"):
            WorkerConfig(WHISPER_MODEL="")


class TestWhisperModelSize:
    def test_large_v3(self):
        config = WorkerConfig(WHISPER_MODEL="large-v3")
        assert config.whisper_model_size == "large"

    def test_tiny(self):
        config = WorkerConfig(WHISPER_MODEL="tiny")
        assert config.whisper_model_size == "tiny"

    def test_base(self):
        config = WorkerConfig(WHISPER_MODEL="base")
        assert config.whisper_model_size == "base"

    def test_small(self):
        config = WorkerConfig(WHISPER_MODEL="small")
        assert config.whisper_model_size == "small"

    def test_medium(self):
        config = WorkerConfig(WHISPER_MODEL="medium")
        assert config.whisper_model_size == "medium"


class TestMaxTaskDurationValidation:
    def test_zero_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            WorkerConfig(MAX_TASK_DURATION=0)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            WorkerConfig(MAX_TASK_DURATION=-100)

    def test_valid_duration(self):
        config = WorkerConfig(MAX_TASK_DURATION=600)
        assert config.MAX_TASK_DURATION == 600

    def test_default_900(self):
        config = WorkerConfig()
        assert config.MAX_TASK_DURATION == 900


class TestMaxRetriesValidation:
    def test_negative_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            WorkerConfig(MAX_RETRIES=-1)

    def test_zero_is_valid(self):
        config = WorkerConfig(MAX_RETRIES=0)
        assert config.MAX_RETRIES == 0

    def test_positive_valid(self):
        config = WorkerConfig(MAX_RETRIES=5)
        assert config.MAX_RETRIES == 5

    def test_default_3(self):
        config = WorkerConfig()
        assert config.MAX_RETRIES == 3


class TestProperties:
    def test_redis_url(self):
        config = WorkerConfig(REDIS_HOST="my-redis", REDIS_PORT=6380)
        assert config.redis_url == "redis://my-redis:6380"

    def test_data_dir_path(self):
        config = WorkerConfig(DATA_DIR="/data")
        assert config.data_dir_path == Path("/data")

    def test_data_dir_path_custom(self):
        config = WorkerConfig(DATA_DIR="/tmp/briefer")
        assert config.data_dir_path == Path("/tmp/briefer")
