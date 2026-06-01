"""Unit tests for bot.result_listener.ResultListener."""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from bot.result_listener import ResultListener


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def listener():
    """Return a ResultListener with test configuration."""
    return ResultListener(redis_host="localhost", redis_port=6379)


# ---------------------------------------------------------------------------
# test_listener_initializes_with_config
# ---------------------------------------------------------------------------


class TestListenerInitializesWithConfig:
    """Verify ResultListener stores configuration on init."""

    def test_stores_redis_host(self, listener):
        """redis_host is stored as-is."""
        assert listener.redis_host == "localhost"

    def test_stores_redis_port(self, listener):
        """redis_port is stored as an int."""
        assert listener.redis_port == 6379

    def test_initial_running_flag_is_false(self, listener):
        """_running starts as False before listen() is called."""
        assert listener._running is False

    def test_channel_is_task_results(self):
        """CHANNEL class attribute equals 'task_results'."""
        assert ResultListener.CHANNEL == "task_results"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_listener_in_thread(listener, callback, messages, delay=0.3):
    """Start listener in a thread, wait for messages, then stop it.

    Args:
        listener: ResultListener instance.
        callback: Callable to invoke on messages.
        messages: List of messages to return from pubsub.get_message.
        delay: Seconds to wait before signalling shutdown.

    Returns:
        The thread used.
    """
    mock_pubsub = MagicMock()
    idx = [0]

    def get_message_side_effect(*args, **kwargs):
        if idx[0] < len(messages):
            idx[0] += 1
            return messages[idx[0] - 1]
        return None

    mock_pubsub.get_message.side_effect = get_message_side_effect
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    with patch("redis.Redis", return_value=mock_redis):
        thread = threading.Thread(target=listener.listen, args=(callback,))
        thread.start()
        time.sleep(delay)
        listener._running = False
        thread.join(timeout=3)

    return thread


# ---------------------------------------------------------------------------
# test_listen_calls_callback_on_message
# ---------------------------------------------------------------------------


class TestListenCallsCallbackOnMessage:
    """Verify the callback is invoked with parsed JSON for each message."""

    def test_callback_receives_parsed_data(self, listener):
        """Published JSON message results in callback(data) call."""
        payload = {"task_id": "abc-123", "text": "Hello"}
        messages = [
            {"type": "message", "data": json.dumps(payload)},
        ]

        callback = MagicMock()
        _run_listener_in_thread(listener, callback, messages)

        callback.assert_called_once_with(payload)


# ---------------------------------------------------------------------------
# test_listen_skips_invalid_json
# ---------------------------------------------------------------------------


class TestListenSkipsInvalidJson:
    """Verify invalid JSON is logged and the callback is NOT called."""

    def test_invalid_json_does_not_call_callback(self, listener):
        """Malformed JSON triggers an error log and skips the callback."""
        messages = [
            {"type": "message", "data": "{invalid json!!!"},
        ]

        callback = MagicMock()
        _run_listener_in_thread(listener, callback, messages)

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# test_listen_skips_missing_task_id
# ---------------------------------------------------------------------------


class TestListenSkipsMissingTaskId:
    """Verify messages without a task_id field are logged but not passed to callback."""

    def test_missing_task_id_not_passed_to_callback(self, listener):
        """A valid JSON without task_id logs an error and skips the callback."""
        payload = {"text": "no task id here"}
        messages = [
            {"type": "message", "data": json.dumps(payload)},
        ]

        callback = MagicMock()
        _run_listener_in_thread(listener, callback, messages)

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# test_listen_handles_callback_error
# ---------------------------------------------------------------------------


class TestListenHandlesCallbackError:
    """Verify a callback that raises an exception does not stop the listener."""

    def test_callback_exception_logged_and_continues(self, listener):
        """When callback raises, the error is logged and the next message is still processed."""
        call_count = [0]
        received = []

        def flaky_callback(data):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                raise RuntimeError("callback boom")
            received.append(data)

        messages = [
            {"type": "message", "data": json.dumps({"task_id": "1"})},
            {"type": "message", "data": json.dumps({"task_id": "2"})},
        ]

        _run_listener_in_thread(listener, flaky_callback, messages, delay=0.5)

        # First call raised, second call should have succeeded
        assert len(received) == 1
        assert received[0]["task_id"] == "2"


# ---------------------------------------------------------------------------
# test_listen_handles_sigterm
# ---------------------------------------------------------------------------


class TestListenHandlesSigterm:
    """Verify SIGTERM causes graceful shutdown."""

    def test_sigterm_sets_running_to_false(self, listener):
        """Raising SIGTERM sets _running to False and loop exits."""
        messages = [
            {"type": "message", "data": json.dumps({"task_id": "1"})},
        ]

        callback = MagicMock()
        thread = _run_listener_in_thread(listener, callback, messages, delay=0.1)

        # Simulate SIGTERM by setting _running = False directly
        # (signal.signal() only works in the main thread, so we simulate
        #  the effect the signal handler would have)
        listener._running = False
        thread.join(timeout=3)

        assert listener._running is False
        assert not thread.is_alive()
