"""Unit tests for bot/logging_setup.py."""

import json
import logging

import pytest

from bot.logging_setup import JsonFormatter, setup_logging


class TestSetupLoggingCreatesJsonFormatter:
    """Verify that setup_logging installs a JSON formatter."""

    def test_json_formatter_output_structure(self):
        """JsonFormatter produces a dict with all required keys."""
        formatter = JsonFormatter("test-svc")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert "timestamp" in data
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert data["service"] == "test-svc"

    def test_json_formatter_service_name(self):
        """JsonFormatter embeds the correct service name."""
        formatter = JsonFormatter("my-worker")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=1,
            msg="msg",
            args=(),
            exc_info=None,
        )
        data = json.loads(formatter.format(record))
        assert data["service"] == "my-worker"


class TestLogInfoOutputsJson:
    """INFO-level log records produce valid JSON on stdout."""

    def test_info_level_json_output(self, capsys):
        """Captured stdout contains valid JSON with level INFO."""
        setup_logging(service="test-info", level="INFO")
        logger = logging.getLogger("test-info")
        logger.info("test info message")

        captured = capsys.readouterr()
        assert captured.out.strip() != "", "Expected log output on stdout"

        # setup_logging emits an "initialized" line; parse the last line.
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        data = json.loads(lines[-1])
        assert data["level"] == "INFO"
        assert data["message"] == "test info message"
        assert data["service"] == "test-info"


class TestLogErrorOutputsJson:
    """ERROR-level log records produce valid JSON on stdout."""

    def test_error_level_json_output(self, capsys):
        """Captured stdout contains valid JSON with level ERROR."""
        setup_logging(service="test-error", level="ERROR")
        logger = logging.getLogger("test-error")
        logger.error("test error message")

        captured = capsys.readouterr()
        assert captured.out.strip() != "", "Expected log output on stdout"

        data = json.loads(captured.out.strip())
        assert data["level"] == "ERROR"
        assert data["message"] == "test error message"
        assert data["service"] == "test-error"

    def test_error_level_with_exception(self, capsys):
        """ERROR log with exc_info includes exception field."""
        setup_logging(service="test-exc", level="ERROR")
        logger = logging.getLogger("test-exc")
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("caught exception")

        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError: boom" in data["exception"]


class TestInvalidLevelRaises:
    """Invalid log levels must raise ValueError."""

    def test_trace_level_raises(self):
        with pytest.raises(ValueError, match="Invalid log level"):
            setup_logging(service="test", level="TRACE")

    def test_numeric_level_raises(self):
        with pytest.raises(ValueError, match="Invalid log level"):
            setup_logging(service="test", level="10")

    def test_empty_level_defaults_to_info(self):
        """Empty string level defaults to INFO (does not raise)."""
        # Should not raise
        setup_logging(service="test-empty", level="")
        logger = logging.getLogger("test-empty")
        assert logger.level == logging.INFO


class TestDefaultLevelIsInfo:
    """Default (no level argument) should be INFO."""

    def test_default_level_is_info(self, capsys):
        """Calling setup_logging without level sets INFO."""
        setup_logging(service="test-default")
        logger = logging.getLogger("test-default")
        assert logger.level == logging.INFO

        logger.info("default level test")
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        data = json.loads(lines[-1])
        assert data["level"] == "INFO"


class TestHandlerDeduplication:
    """Repeated calls to setup_logging should not add duplicate handlers."""

    def test_no_duplicate_handlers(self):
        setup_logging(service="test-dedup", level="INFO")
        logger = logging.getLogger("test-dedup")
        first_count = len(logger.handlers)

        setup_logging(service="test-dedup", level="INFO")
        assert len(logger.handlers) == first_count
