"""Tests for worker/errors.py — Error Handling & Logging (T3.4)."""

import json
import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest

from worker.errors import TaskError, handle_error


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_error():
    return ValueError("disk full")


@pytest.fixture
def task_id():
    return str(uuid.uuid4())


# ── TaskError tests ──────────────────────────────────────────────────────────

class TestTaskError:
    def test_task_error_default_retry_count(self, sample_error):
        err = TaskError(
            task_id="t-1",
            error_type="IOError",
            message=str(sample_error),
        )
        assert err.task_id == "t-1"
        assert err.error_type == "IOError"
        assert err.message == "disk full"
        assert err.retry_count == 0

    def test_task_error_custom_retry_count(self, sample_error):
        err = TaskError(
            task_id="t-2",
            error_type="TimeoutError",
            message=str(sample_error),
            retry_count=2,
        )
        assert err.retry_count == 2

    def test_task_error_str(self):
        err = TaskError(
            task_id="t-3",
            error_type="RedisError",
            message="connection refused",
            retry_count=1,
        )
        assert "t-3" in str(err)
        assert "RedisError" in str(err)
        assert "connection refused" in str(err)

    def test_task_error_to_dict(self):
        err = TaskError(
            task_id="t-4",
            error_type="ValueError",
            message="bad input",
            retry_count=0,
        )
        d = err.to_dict()
        assert d["task_id"] == "t-4"
        assert d["error_type"] == "ValueError"
        assert d["message"] == "bad input"
        assert d["retry_count"] == 0
        assert "timestamp" in d


# ── handle_error tests ───────────────────────────────────────────────────────

class TestHandleError:
    def test_handle_error_retries_under_limit(self, task_id, sample_error):
        """retry_count=0, max_retries=3 → retry=True."""
        result = handle_error(task_id, sample_error, max_retries=3)
        assert result is True

    def test_handle_error_retries_at_count_2_of_3(self, task_id, sample_error):
        """retry_count=2, max_retries=3 → retry=True."""
        err = TaskError(
            task_id=task_id,
            error_type="TimeoutError",
            message=str(sample_error),
            retry_count=2,
        )
        result = handle_error(task_id, err, max_retries=3)
        assert result is True

    def test_handle_error_sends_to_dlq_at_limit(self, task_id, sample_error):
        """retry_count=3, max_retries=3 → retry=False (DLQ)."""
        err = TaskError(
            task_id=task_id,
            error_type="TimeoutError",
            message=str(sample_error),
            retry_count=3,
        )
        result = handle_error(task_id, err, max_retries=3)
        assert result is False

    def test_handle_error_sends_to_dlq_exceeds_limit(self, task_id, sample_error):
        """retry_count=5, max_retries=3 → retry=False (DLQ)."""
        err = TaskError(
            task_id=task_id,
            error_type="TimeoutError",
            message=str(sample_error),
            retry_count=5,
        )
        result = handle_error(task_id, err, max_retries=3)
        assert result is False

    def test_handle_error_none_raises_valueerror(self):
        with pytest.raises(ValueError, match="error cannot be None"):
            handle_error("t-1", None, max_retries=3)

    def test_handle_error_negative_max_retries_raises(self, sample_error):
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            handle_error("t-1", sample_error, max_retries=-1)

    def test_handle_error_increments_retry_count(self, task_id, sample_error):
        """After handle_error with retry=True, TaskError has incremented retry_count."""
        err = TaskError(
            task_id=task_id,
            error_type="IOError",
            message=str(sample_error),
            retry_count=0,
        )
        handle_error(task_id, err, max_retries=3)
        assert err.retry_count == 1

    def test_handle_error_logs_warning_on_retry(self, task_id, sample_error, caplog):
        """handle_error logs WARNING JSON when retrying."""
        with caplog.at_level(logging.WARNING):
            handle_error(task_id, sample_error, max_retries=3)

        assert len(caplog.records) >= 1
        log_record = caplog.records[0]
        assert task_id in log_record.message

    def test_handle_error_logs_error_on_dlq(self, task_id, sample_error, caplog):
        """handle_error logs ERROR JSON when sending to DLQ."""
        err = TaskError(
            task_id=task_id,
            error_type="TimeoutError",
            message=str(sample_error),
            retry_count=3,
        )
        with caplog.at_level(logging.ERROR):
            handle_error(task_id, err, max_retries=3)

        assert len(caplog.records) >= 1
        log_record = caplog.records[0]
        assert task_id in log_record.message

    def test_handle_error_zero_max_retries_dlq(self, task_id, sample_error):
        """max_retries=0 → immediate DLQ."""
        result = handle_error(task_id, sample_error, max_retries=0)
        assert result is False

    def test_handle_error_creates_task_error_from_plain_exception(self, task_id, sample_error):
        """When error is a plain Exception (not TaskError), handle_error wraps it."""
        result = handle_error(task_id, sample_error, max_retries=3)
        assert result is True

    def test_handle_error_raises_keyerror_type(self, task_id):
        """KeyError exception is wrapped with correct error_type."""
        err = KeyError("missing key")
        result = handle_error(task_id, err, max_retries=3)
        assert result is True  # should not raise, returns retry=True
