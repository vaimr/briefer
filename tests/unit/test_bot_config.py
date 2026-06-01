"""Unit tests for bot/config.py."""

import pytest

from bot.config import BotConfig


class TestDefaultValues:
    def test_default_values(self):
        config = BotConfig()
        assert config.REDIS_HOST == "redis"
        assert config.REDIS_PORT == 6379
        assert config.LOG_LEVEL == "INFO"
        assert config.HEALTH_PORT == 8081
        assert config.TZ == "Europe/Moscow"

    def test_default_empty_matrix_fields(self):
        config = BotConfig()
        assert config.MATRIX_HOMESERVER == ""
        assert config.MATRIX_USER == ""
        assert config.MATRIX_PASSWORD == ""
        assert config.MATRIX_ACCESS_TOKEN == ""


class TestHomeserverValidation:
    def test_adds_https(self):
        config = BotConfig(MATRIX_HOMESERVER="matrix.example.com")
        assert config.MATRIX_HOMESERVER == "https://matrix.example.com"

    def test_strips_trailing_slash(self):
        config = BotConfig(MATRIX_HOMESERVER="https://example.com/")
        assert config.MATRIX_HOMESERVER == "https://example.com"

    def test_preserves_https(self):
        config = BotConfig(MATRIX_HOMESERVER="https://example.com")
        assert config.MATRIX_HOMESERVER == "https://example.com"

    def test_preserves_http(self):
        config = BotConfig(MATRIX_HOMESERVER="http://localhost:8000")
        assert config.MATRIX_HOMESERVER == "http://localhost:8000"

    def test_empty_homeserver_allowed_at_construction(self):
        """Empty MATRIX_HOMESERVER is allowed at construction;
        validate_required() will raise at runtime."""
        config = BotConfig(MATRIX_HOMESERVER="")
        assert config.MATRIX_HOMESERVER == ""

    def test_empty_homeserver_raises_validate_required(self):
        config = BotConfig(MATRIX_HOMESERVER="", MATRIX_USER="@bot:example.com")
        with pytest.raises(ValueError, match="MATRIX_HOMESERVER is required"):
            config.validate_required()


class TestUserValidation:
    def test_requires_at(self):
        with pytest.raises(ValueError, match="must start with @"):
            BotConfig(MATRIX_USER="bot:example.com")

    def test_accepts_valid_mxid(self):
        config = BotConfig(MATRIX_USER="@bot:example.com")
        assert config.MATRIX_USER == "@bot:example.com"

    def test_empty_user_allowed_at_construction(self):
        """Empty MATRIX_USER is allowed at construction;
        validate_required() will raise at runtime."""
        config = BotConfig(MATRIX_USER="")
        assert config.MATRIX_USER == ""

    def test_empty_user_raises_validate_required(self):
        config = BotConfig(MATRIX_HOMESERVER="https://example.com", MATRIX_USER="")
        with pytest.raises(ValueError, match="MATRIX_USER is required"):
            config.validate_required()


class TestRedisPortValidation:
    def test_zero_raises(self):
        with pytest.raises(ValueError, match="between 1 and 65535"):
            BotConfig(REDIS_PORT=0)

    def test_65536_raises(self):
        with pytest.raises(ValueError, match="between 1 and 65535"):
            BotConfig(REDIS_PORT=65536)

    def test_valid_range(self):
        config = BotConfig(REDIS_PORT=6379)
        assert config.REDIS_PORT == 6379

    def test_boundary_1(self):
        config = BotConfig(REDIS_PORT=1)
        assert config.REDIS_PORT == 1

    def test_boundary_65535(self):
        config = BotConfig(REDIS_PORT=65535)
        assert config.REDIS_PORT == 65535


class TestLogLevelValidation:
    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="must be one of"):
            BotConfig(LOG_LEVEL="TRACE")

    def test_uppercased(self):
        config = BotConfig(LOG_LEVEL="info")
        assert config.LOG_LEVEL == "INFO"

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_valid_levels(self, level):
        config = BotConfig(LOG_LEVEL=level)
        assert config.LOG_LEVEL == level


class TestValidateRequired:
    def test_no_error_when_both_set(self):
        config = BotConfig(
            MATRIX_HOMESERVER="https://example.com",
            MATRIX_USER="@bot:example.com",
        )
        config.validate_required()  # should not raise

    def test_error_when_homeserver_empty(self):
        config = BotConfig(MATRIX_USER="@bot:example.com")
        with pytest.raises(ValueError, match="MATRIX_HOMESERVER is required"):
            config.validate_required()

    def test_error_when_user_empty(self):
        config = BotConfig(MATRIX_HOMESERVER="https://example.com")
        with pytest.raises(ValueError, match="MATRIX_USER is required"):
            config.validate_required()

    def test_error_when_both_empty(self):
        config = BotConfig()
        with pytest.raises(ValueError, match="MATRIX_HOMESERVER is required"):
            config.validate_required()


class TestProperties:
    def test_redis_url(self):
        config = BotConfig(REDIS_HOST="my-redis", REDIS_PORT=6380)
        assert config.redis_url == "redis://my-redis:6380"

    def test_matrix_user_display_name(self):
        config = BotConfig(MATRIX_USER="@bot:example.com")
        assert config.matrix_user_display_name == "bot"

    def test_matrix_user_display_name_with_subdomain(self):
        config = BotConfig(MATRIX_USER="@bot:sub.example.com")
        assert config.matrix_user_display_name == "bot"

    def test_matrix_user_display_name_single_part(self):
        config = BotConfig(MATRIX_USER="@bot")
        assert config.matrix_user_display_name == "bot"

    def test_matrix_client_config(self):
        config = BotConfig(
            MATRIX_HOMESERVER="https://example.com",
            MATRIX_USER="@bot:example.com",
            MATRIX_PASSWORD="secret",
            TZ="UTC",
        )
        expected = {
            "homeserver_url": "https://example.com",
            "user": "@bot:example.com",
            "password": "secret",
            "device_name": "briefer-bot-UTC",
        }
        assert config.matrix_client_config == expected

    def test_matrix_client_config_with_normalized_url(self):
        config = BotConfig(
            MATRIX_HOMESERVER="example.com/",
            MATRIX_USER="@bot:example.com",
            MATRIX_PASSWORD="secret",
            TZ="UTC",
        )
        expected = {
            "homeserver_url": "https://example.com",
            "user": "@bot:example.com",
            "password": "secret",
            "device_name": "briefer-bot-UTC",
        }
        assert config.matrix_client_config == expected
