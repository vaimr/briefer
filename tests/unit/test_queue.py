"""Tests for Redis queue enqueue_task / dequeue_task functions."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from redis import ConnectionError as RedisConnectionError

# Mock heavy worker dependencies before importing worker.__main__
sys.modules["worker.health"] = MagicMock()
sys.modules["worker.llm_engine"] = MagicMock()
sys.modules["worker.metrics"] = MagicMock()
sys.modules["worker.whisper_engine"] = MagicMock()

from bot.client import enqueue_task
from worker.__main__ import dequeue_task


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Return a fresh MagicMock acting as a Redis client."""
    conn = MagicMock()
    conn.rpush.return_value = 1
    conn.blpop.return_value = None
    return conn


@pytest.fixture
def valid_room_id():
    return "room-abc-123"


@pytest.fixture
def valid_audio_path():
    return "/data/audio/meeting.wav"


# ---------------------------------------------------------------------------
# enqueue_task tests
# ---------------------------------------------------------------------------


class TestEnqueueTaskFormatsCorrectly:
    """Verify the task string format is ``room_id|audio_path``."""

    def test_format_contains_pipe_separator(self, mock_redis, valid_room_id, valid_audio_path):
        """Task string uses ``|`` as separator between room_id and audio_path."""
        result = enqueue_task(mock_redis, valid_room_id, valid_audio_path)
        assert "|" in result
        parts = result.split("|", 1)
        assert parts[0] == valid_room_id
        assert parts[1] == valid_audio_path

    def test_format_with_spaces_in_path(self, mock_redis):
        """Path containing spaces is preserved verbatim."""
        path = "/data/audio/my meeting.wav"
        result = enqueue_task(mock_redis, "room-1", path)
        assert result == "room-1|/data/audio/my meeting.wav"


class TestEnqueueTaskPushesToQueue:
    """Verify rpush is called with correct arguments."""

    def test_rpush_called_with_queue_name(self, mock_redis, valid_room_id, valid_audio_path):
        """rpush is invoked on the ``transcription_queue`` key."""
        enqueue_task(mock_redis, valid_room_id, valid_audio_path)
        mock_redis.rpush.assert_called_once_with("transcription_queue", valid_room_id + "|" + valid_audio_path)

    def test_rpush_called_with_correct_task_string(self, mock_redis, valid_room_id, valid_audio_path):
        """The second argument to rpush is the formatted task string."""
        enqueue_task(mock_redis, valid_room_id, valid_audio_path)
        expected_task = f"{valid_room_id}|{valid_audio_path}"
        call_args = mock_redis.rpush.call_args
        assert call_args[0][1] == expected_task


class TestEnqueueTaskReturnsTask:
    """Verify the return value is the formatted task string."""

    def test_returns_formatted_string(self, mock_redis, valid_room_id, valid_audio_path):
        """Return value equals ``f"{room_id}|{audio_path}"``."""
        result = enqueue_task(mock_redis, valid_room_id, valid_audio_path)
        expected = f"{valid_room_id}|{valid_audio_path}"
        assert result == expected

    def test_returns_same_string_passed_to_rpush(self, mock_redis, valid_room_id, valid_audio_path):
        """The returned string is identical to what was pushed to Redis."""
        result = enqueue_task(mock_redis, valid_room_id, valid_audio_path)
        _, pushed_value = mock_redis.rpush.call_args[0]
        assert result == pushed_value


class TestEnqueueTaskEmptyRoomRaises:
    """Verify ValueError is raised for empty inputs."""

    def test_empty_room_id_raises(self, mock_redis, valid_audio_path):
        """ValueError is raised when room_id is an empty string."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            enqueue_task(mock_redis, "", valid_audio_path)

    def test_whitespace_only_room_id_raises(self, mock_redis, valid_audio_path):
        """ValueError is raised when room_id contains only whitespace."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            enqueue_task(mock_redis, "   ", valid_audio_path)

    def test_empty_audio_path_raises(self, mock_redis, valid_room_id):
        """ValueError is raised when audio_path is an empty string."""
        with pytest.raises(ValueError, match="audio_path must not be empty"):
            enqueue_task(mock_redis, valid_room_id, "")

    def test_whitespace_only_audio_path_raises(self, mock_redis, valid_room_id):
        """ValueError is raised when audio_path contains only whitespace."""
        with pytest.raises(ValueError, match="audio_path must not be empty"):
            enqueue_task(mock_redis, valid_room_id, "   ")


class TestEnqueueTaskConnectionError:
    """Verify ConnectionError is raised when Redis is unreachable."""

    def test_redis_connection_error_wrapped(self, valid_room_id, valid_audio_path):
        """ConnectionError wraps RedisConnectionError when Redis fails."""
        mock_conn = MagicMock()
        mock_conn.rpush.side_effect = RedisConnectionError("Connection refused")

        with pytest.raises(ConnectionError, match="Redis connection failed"):
            enqueue_task(mock_conn, valid_room_id, valid_audio_path)


# ---------------------------------------------------------------------------
# dequeue_task tests
# ---------------------------------------------------------------------------


class TestDequeueTaskReturnsTask:
    """Verify dequeue_task correctly parses and returns tasks."""

    def test_returns_tuple_from_valid_entry(self, mock_redis, valid_room_id, valid_audio_path):
        """Valid queue entry returns ``(room_id, audio_path)`` tuple."""
        task = f"{valid_room_id}|{valid_audio_path}"
        mock_redis.blpop.return_value = (b"transcription_queue", task.encode())

        result = dequeue_task(mock_redis)

        assert result == (valid_room_id, valid_audio_path)

    def test_returns_tuple_with_complex_path(self, mock_redis):
        """Path with multiple ``|``-like characters is handled correctly."""
        room = "room-1"
        path = "/data/audio/file|extra|part.wav"
        task = f"{room}|{path}"
        mock_redis.blpop.return_value = (b"transcription_queue", task.encode())

        result = dequeue_task(mock_redis)

        # split("|", 1) ensures only the first pipe is the separator
        assert result == (room, path)

    def test_blpop_called_with_correct_args(self, mock_redis):
        """blpop is called on ``transcription_queue`` with timeout=5."""
        dequeue_task(mock_redis)
        mock_redis.blpop.assert_called_once_with("transcription_queue", timeout=5)


class TestDequeueTaskReturnsNoneOnTimeout:
    """Verify None is returned when the queue is empty (timeout)."""

    def test_none_when_blpop_returns_none(self, mock_redis):
        """blpop returning None (timeout) yields None from dequeue_task."""
        mock_redis.blpop.return_value = None
        result = dequeue_task(mock_redis)
        assert result is None

    def test_none_when_queue_is_empty(self, mock_redis):
        """Empty queue scenario returns None."""
        mock_redis.blpop.return_value = None
        assert dequeue_task(mock_redis) is None


class TestDequeueTaskConnectionError:
    """Verify ConnectionError is raised when Redis is unreachable."""

    def test_redis_connection_error_wrapped(self):
        """ConnectionError wraps the underlying Redis error."""
        mock_conn = MagicMock()
        mock_conn.blpop.side_effect = RedisConnectionError("Connection refused")

        with pytest.raises(ConnectionError, match="Redis connection failed"):
            dequeue_task(mock_conn)
