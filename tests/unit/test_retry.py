"""Tests for worker.retry — retry decorator with exponential backoff."""

import time
from unittest.mock import patch

import pytest

from worker.retry import TRANSIENT_ERRORS, retry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_failing_function(fail_count: int):
    """Return a function that raises on its first *fail_count* calls."""
    call_count = 0

    def func():
        nonlocal call_count
        call_count += 1
        if call_count <= fail_count:
            raise TRANSIENT_ERRORS[0]("transient failure")
        return "ok"

    return func


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------

class TestSuccessCases:
    """Tests where the function eventually succeeds."""

    def test_retry_succeeds_on_first_attempt(self):
        """Function succeeds immediately — no retries."""
        call_count = 0

        @retry(max_retries=3)
        def func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = func()
        assert result == "ok"
        assert call_count == 1

    def test_retry_succeeds_on_second_attempt(self):
        """Function fails once, succeeds on the second attempt."""
        func = _make_failing_function(fail_count=1)
        decorated = retry(max_retries=3)(func)

        result = decorated()
        assert result == "ok"

    def test_retry_succeeds_on_third_attempt(self):
        """Function fails twice, succeeds on the third attempt."""
        func = _make_failing_function(fail_count=2)
        decorated = retry(max_retries=3)(func)

        result = decorated()
        assert result == "ok"


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------

class TestFailureCases:
    """Tests where the function exhausts all retries."""

    def test_retry_fails_after_max_retries(self):
        """Function fails N times → raises the last exception."""
        func = _make_failing_function(fail_count=3)
        decorated = retry(max_retries=3)(func)

        with pytest.raises(TRANSIENT_ERRORS[0]):
            decorated()

    def test_retry_raises_last_exception(self):
        """When all retries are exhausted, the last exception is raised."""
        errors = [
            ConnectionError("first"),
            TimeoutError("second"),
            ConnectionError("third"),
        ]
        call_count = 0

        @retry(max_retries=3)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise errors[call_count - 1]
            return "ok"

        with pytest.raises(ConnectionError) as exc_info:
            func()
        assert str(exc_info.value) == "third"


# ---------------------------------------------------------------------------
# Back-off timing
# ---------------------------------------------------------------------------

class TestExponentialBackoff:
    """Tests that verify exponential back-off delays."""

    def test_retry_exponential_backoff(self):
        """Delays follow base_delay * 2^attempt: 1s, 2s, 4s."""
        base_delay = 1.0
        call_count = 0

        @retry(max_retries=4, base_delay=base_delay)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ConnectionError("transient")
            return "ok"

        start = time.monotonic()
        func()
        elapsed = time.monotonic() - start

        # Expected total delay: 1.0 + 2.0 + 4.0 = 7.0 seconds
        expected_total = base_delay * (2**0 + 2**1 + 2**2)
        # Allow 1 second tolerance for CI timing variance
        assert elapsed >= expected_total - 1.0
        assert elapsed < expected_total + 1.0


# ---------------------------------------------------------------------------
# Permanent errors — no retry
# ---------------------------------------------------------------------------

class TestPermanentErrors:
    """Tests that permanent errors are NOT retried."""

    def test_retry_does_not_retry_value_error(self):
        """ValueError is raised immediately without retry."""
        call_count = 0

        @retry(max_retries=3)
        def func():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent error"):
            func()
        assert call_count == 1

    def test_retry_does_not_retry_type_error(self):
        """TypeError is raised immediately without retry."""
        call_count = 0

        @retry(max_retries=3)
        def func():
            nonlocal call_count
            call_count += 1
            raise TypeError("type mismatch")

        with pytest.raises(TypeError, match="type mismatch"):
            func()
        assert call_count == 1


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestLogging:
    """Tests that verify logging behaviour."""

    def test_retry_logs_each_attempt(self):
        """Each transient-failure attempt produces a WARNING log."""
        call_count = 0

        @retry(max_retries=3, base_delay=0.001)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        with patch("worker.retry.logger.warning") as mock_warning:
            func()

        # 2 failures → 2 log calls
        assert mock_warning.call_count == 2
        for i, call_args in enumerate(mock_warning.call_args_list):
            args = call_args[0]
            format_str = args[0]
            func_name = args[1]
            attempt_num = args[2]
            assert "failed" in format_str
            assert func_name == "func"
            assert attempt_num == i + 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Additional edge-case coverage."""

    def test_retry_zero_max_retries(self):
        """max_retries=0 means no attempts — function is never called."""
        called = False

        @retry(max_retries=0)
        def func():
            nonlocal called
            called = True

        func()
        assert called is False

    def test_retry_preserves_function_metadata(self):
        """functools.wraps preserves __name__ and __doc__."""
        @retry(max_retries=1)
        def my_function():
            """My docstring."""
            return 42

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_retry_with_kwargs(self):
        """Retry works correctly with keyword arguments."""
        @retry(max_retries=2, base_delay=0.001)
        def add(a, b=0):
            return a + b

        result = add(10, b=5)
        assert result == 15
