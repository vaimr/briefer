"""Unit tests for worker.result_publisher.ResultPublisher."""

from unittest.mock import MagicMock, patch

import pytest

from worker.result_publisher import ResultPublisher

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Return a fresh MagicMock acting as a Redis client."""
    conn = MagicMock()
    return conn


@pytest.fixture
def publisher(mock_redis):
    """Return a ResultPublisher with a mocked Redis connection."""
    with patch("worker.result_publisher.redis.Redis", return_value=mock_redis):
        pub = ResultPublisher(redis_host="localhost", redis_port=6379)
    return pub


@pytest.fixture
def valid_transcription():
    """Return a minimal valid transcription dict."""
    return {"text": "Hello world"}


@pytest.fixture
def valid_pdf_path(tmp_path):
    """Return a Path to a real temporary file (simulating a PDF)."""
    pdf = tmp_path / "result.pdf"
    pdf.write_text("fake pdf")
    return pdf


# ---------------------------------------------------------------------------
# test_publisher_initializes_with_redis
# ---------------------------------------------------------------------------


class TestPublisherInitializesWithRedis:
    """Verify ResultPublisher creates a Redis connection on init."""

    def test_redis_called_with_correct_host_port(self, mock_redis):
        """redis.Redis is instantiated with the passed host and port."""
        with patch("worker.result_publisher.redis.Redis", return_value=mock_redis) as mock_cls:
            ResultPublisher(redis_host="myhost", redis_port=6380)
            mock_cls.assert_called_once_with(
                host="myhost",
                port=6380,
                decode_responses=True,
            )

    def test_redis_connection_is_stored(self, publisher):
        """The publisher stores the Redis client on self.redis."""
        assert publisher.redis is not None


# ---------------------------------------------------------------------------
# test_publish_result_sends_message
# ---------------------------------------------------------------------------


class TestPublishResultSendsMessage:
    """Verify publish_result sends a JSON message to the correct channel."""

    def test_publish_calls_redis_publish(self, publisher, mock_redis, valid_pdf_path, valid_transcription):
        """redis.publish is called exactly once with the channel and JSON string."""
        publisher.publish_result("task-1", valid_transcription, valid_pdf_path)
        mock_redis.publish.assert_called_once()

    def test_publish_channel_is_task_results(self, publisher, mock_redis, valid_pdf_path, valid_transcription):
        """The first argument to redis.publish is the CHANNEL name."""
        publisher.publish_result("task-1", valid_transcription, valid_pdf_path)
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == ResultPublisher.CHANNEL


# ---------------------------------------------------------------------------
# test_publish_result_empty_task_id_raises
# ---------------------------------------------------------------------------


class TestPublishResultEmptyTaskIdRaises:
    """Verify ValueError is raised for invalid task_id values."""

    def test_empty_string_raises(self, publisher, valid_pdf_path, valid_transcription):
        """Empty string task_id raises ValueError."""
        with pytest.raises(ValueError, match="task_id is required"):
            publisher.publish_result("", valid_transcription, valid_pdf_path)

    def test_whitespace_only_raises(self, publisher, valid_pdf_path, valid_transcription):
        """Whitespace-only task_id raises ValueError."""
        with pytest.raises(ValueError, match="task_id is required"):
            publisher.publish_result("   ", valid_transcription, valid_pdf_path)


# ---------------------------------------------------------------------------
# test_publish_result_missing_pdf_raises
# ---------------------------------------------------------------------------


class TestPublishResultMissingPdfRaises:
    """Verify FileNotFoundError is raised when PDF does not exist."""

    def test_nonexistent_path_raises(self, publisher, valid_transcription):
        """Path that does not exist raises FileNotFoundError."""
        import pathlib

        missing = pathlib.Path("/tmp/nonexistent_briefer_test_12345.pdf")
        with pytest.raises(FileNotFoundError, match="PDF not found"):
            publisher.publish_result("task-1", valid_transcription, missing)


# ---------------------------------------------------------------------------
# test_publish_result_json_format
# ---------------------------------------------------------------------------


class TestPublishResultJsonFormat:
    """Verify the published JSON contains all required fields."""

    def test_json_contains_all_fields(self, publisher, mock_redis, valid_pdf_path, valid_transcription):
        """Published JSON includes task_id, transcription, summary, pdf_path, timestamp."""
        summary_text = "This is a summary"
        transcription = {"text": "Hello world", "summary": summary_text}
        publisher.publish_result("task-abc", transcription, valid_pdf_path)

        published_msg = mock_redis.publish.call_args[0][1]
        data = __import__("json").loads(published_msg)

        assert data["task_id"] == "task-abc"
        assert data["transcription"] == "Hello world"
        assert data["summary"] == summary_text
        assert data["pdf_path"] == str(valid_pdf_path)
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)

    def test_json_summary_defaults_to_empty(self, publisher, mock_redis, valid_pdf_path, valid_transcription):
        """When transcription has no 'summary' key, JSON summary defaults to ''."""
        publisher.publish_result("task-2", valid_transcription, valid_pdf_path)
        published_msg = mock_redis.publish.call_args[0][1]
        data = __import__("json").loads(published_msg)
        assert data["summary"] == ""


# ---------------------------------------------------------------------------
# test_publish_result_reconnects_on_disconnect
# ---------------------------------------------------------------------------


class TestPublishResultReconnectsOnDisconnect:
    """Verify publisher can reconnect when Redis connection is lost."""

    def test_reconnect_creates_new_connection(self, mock_redis, valid_pdf_path, valid_transcription):
        new_mock = MagicMock()

        with patch("worker.result_publisher.redis.Redis") as mock_cls:
            mock_cls.side_effect = [mock_redis, new_mock]

            pub = ResultPublisher(redis_host="localhost", redis_port=6379)
            assert pub.redis is mock_redis

            pub2 = ResultPublisher(redis_host="localhost", redis_port=6379)
            assert pub2.redis is new_mock
            assert pub2.redis is not pub.redis

    def test_reconnect_publish_succeeds(self, mock_redis, valid_pdf_path, valid_transcription):
        import redis as redis_pkg

        new_mock = MagicMock()
        new_mock.publish.return_value = 1

        with patch("worker.result_publisher.redis.Redis") as mock_cls:
            mock_redis.publish.side_effect = redis_pkg.ConnectionError("Connection refused")
            mock_cls.side_effect = [mock_redis, new_mock]

            ResultPublisher(redis_host="localhost", redis_port=6379)

            pub2 = ResultPublisher(redis_host="localhost", redis_port=6379)

            pub2.publish_result("task-reconnect", valid_transcription, valid_pdf_path)
            new_mock.publish.assert_called_once()
