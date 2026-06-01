"""Tests for worker/dlq.py — Dead Letter Queue (T6.2)."""

import json
import logging
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from worker.dlq import DeadLetterQueue


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def redis_mock():
    """Return a MagicMock simulating a redis.Redis client."""
    mock = MagicMock()
    mock.llen.return_value = 0
    return mock


@pytest.fixture
def dlq(redis_mock):
    """Return a DeadLetterQueue backed by a mock Redis client."""
    return DeadLetterQueue(redis_mock)


@pytest.fixture
def sample_task_id():
    """Return a random UUID string as a task identifier."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_error():
    """Return a sample exception for testing."""
    return RuntimeError("transcription failed")


@pytest.fixture
def sample_tb():
    """Return a sample traceback string."""
    return "Traceback (most recent call last):\n  File 'main.py', line 1\n    raise RuntimeError('oops')\nRuntimeError: oops"


# ── Initialization tests ────────────────────────────────────────────────────

class TestInitialization:
    def test_dlq_initializes_with_redis(self, redis_mock):
        """DLQ accepts a Redis client and stores it."""
        dlq = DeadLetterQueue(redis_mock)
        assert dlq.redis is redis_mock

    def test_dlq_raises_on_none_redis(self):
        """DLQ raises ValueError when initialized with None."""
        with pytest.raises(ValueError, match="redis_client cannot be None"):
            DeadLetterQueue(None)

    def test_dlq_channel_constant(self, dlq):
        """DLQ uses the correct Redis channel name."""
        assert dlq.CHANNEL == "dlq:transcription"

    def test_dlq_max_size_constant(self, dlq):
        """DLQ uses the correct maximum size."""
        assert dlq.MAX_SIZE == 10000


# ── Add tests ────────────────────────────────────────────────────────────────

class TestAdd:
    def test_dlq_add_adds_message(self, dlq, redis_mock, sample_task_id, sample_error, sample_tb):
        """Adding a task pushes a JSON record to Redis."""
        dlq.add(sample_task_id, sample_error, sample_tb)

        redis_mock.rpush.assert_called_once()
        call_args = redis_mock.rpush.call_args
        assert call_args[0][0] == "dlq:transcription"
        payload = json.loads(call_args[0][1])
        assert payload["task_id"] == sample_task_id
        assert payload["error"] == str(sample_error)
        assert payload["traceback"] == sample_tb
        assert "timestamp" in payload

    def test_dlq_add_empty_task_id_raises(self, dlq):
        """Empty task_id raises ValueError."""
        with pytest.raises(ValueError, match="task_id is required"):
            dlq.add("", RuntimeError("fail"), "tb")

    def test_dlq_add_none_error_raises(self, dlq, sample_task_id):
        """None error raises ValueError."""
        with pytest.raises(ValueError, match="error is required"):
            dlq.add(sample_task_id, None, "tb")

    def test_dlq_add_logs_on_redis_error(self, dlq, sample_task_id, sample_error, sample_tb, caplog):
        """Redis errors are logged but not raised."""
        import redis as redis_lib

        dlq.redis.rpush.side_effect = redis_lib.RedisError("connection lost")
        with caplog.at_level(logging.ERROR):
            dlq.add(sample_task_id, sample_error, sample_tb)

        assert any("Failed to add" in record.message for record in caplog.records)


# ── Get all tests ────────────────────────────────────────────────────────────

class TestGetAll:
    def test_dlq_get_all_returns_messages(self, dlq, redis_mock, sample_task_id, sample_error, sample_tb):
        """get_all returns a list of parsed JSON dicts."""
        message = {
            "task_id": sample_task_id,
            "error": str(sample_error),
            "traceback": sample_tb,
            "timestamp": "2025-01-01T00:00:00",
        }
        redis_mock.lrange.return_value = [json.dumps(message)]

        result = dlq.get_all()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == message

    def test_dlq_get_all_empty_returns_empty_list(self, dlq, redis_mock):
        """Empty DLQ returns an empty list."""
        redis_mock.lrange.return_value = []

        result = dlq.get_all()

        assert result == []


# ── Remove tests ─────────────────────────────────────────────────────────────

class TestRemove:
    def test_dlq_remove_removes_message(self, dlq, redis_mock, sample_task_id, sample_error, sample_tb):
        """Removing by task_id deletes the matching record."""
        message = {
            "task_id": sample_task_id,
            "error": str(sample_error),
            "traceback": sample_tb,
            "timestamp": "2025-01-01T00:00:00",
        }
        redis_mock.lrange.return_value = [json.dumps(message)]

        dlq.remove(sample_task_id)

        redis_mock.lrem.assert_called_once()
        call_args = redis_mock.lrem.call_args
        assert call_args[0][0] == "dlq:transcription"
        assert call_args[0][1] == 1
        assert json.loads(call_args[0][2])["task_id"] == sample_task_id

    def test_dlq_remove_nonexistent_does_nothing(self, dlq, redis_mock, sample_task_id):
        """Removing a non-existent task_id does not call lrem."""
        redis_mock.lrange.return_value = []

        dlq.remove(sample_task_id)

        redis_mock.lrem.assert_not_called()


# ── Overflow / truncation tests ──────────────────────────────────────────────

class TestOverflow:
    def test_dlq_truncates_on_overflow(self, redis_mock):
        """When queue exceeds MAX_SIZE, oldest entries are removed."""
        dlq = DeadLetterQueue(redis_mock)

        # Simulate queue at MAX_SIZE + 3
        redis_mock.llen.side_effect = [10003, 10002, 10001, 10000]

        dlq.add("task-overflow", RuntimeError("fail"), "tb")

        # rpush called once, then lpop called 3 times
        assert redis_mock.rpush.call_count == 1
        assert redis_mock.lpop.call_count == 3

    def test_dlq_no_truncation_under_limit(self, dlq, redis_mock):
        """No truncation when queue is under MAX_SIZE."""
        redis_mock.llen.return_value = 5

        dlq.add("task-ok", RuntimeError("fail"), "tb")

        redis_mock.lpop.assert_not_called()


# ── Message format tests ─────────────────────────────────────────────────────

class TestMessageFormat:
    def test_dlq_message_format(self, dlq, redis_mock, sample_task_id, sample_error, sample_tb):
        """JSON message contains all required fields: task_id, error, traceback, timestamp."""
        dlq.add(sample_task_id, sample_error, sample_tb)

        call_args = redis_mock.rpush.call_args
        payload = json.loads(call_args[0][1])

        assert "task_id" in payload
        assert "error" in payload
        assert "traceback" in payload
        assert "timestamp" in payload
        assert payload["task_id"] == sample_task_id
        assert payload["error"] == str(sample_error)
        assert payload["traceback"] == sample_tb
        # Verify timestamp is a valid ISO format string
        datetime.fromisoformat(payload["timestamp"])
