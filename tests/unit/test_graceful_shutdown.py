"""Tests for worker/graceful_shutdown.py — GracefulShutdown class."""

import signal
from unittest.mock import patch

import pytest

from worker.graceful_shutdown import GracefulShutdown

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def shutdown():
    """A fresh GracefulShutdown instance."""
    return GracefulShutdown()


# ---------------------------------------------------------------------------
# Test: Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_is_running_initially_false(self, shutdown):
        """_running is False before start()."""
        assert shutdown.is_running() is False

    def test_shutdown_requested_initially_false(self, shutdown):
        """_shutdown_requested is False before start()."""
        assert shutdown.shutdown_requested is False

    def test_running_property_initially_false(self, shutdown):
        """running property is False before start()."""
        assert shutdown.running is False


# ---------------------------------------------------------------------------
# Test: start()
# ---------------------------------------------------------------------------


class TestStart:
    def test_start_sets_running_true(self, shutdown):
        """start() sets _running to True."""
        shutdown.start()
        assert shutdown.is_running() is True
        assert shutdown.running is True

    def test_start_registers_signal_handlers(self, shutdown):
        """start() registers handlers for SIGTERM and SIGINT."""
        with patch("worker.graceful_shutdown.signal.signal") as mock_signal:
            shutdown.start()
            assert mock_signal.call_count == 2
            signals_called = {c[0][0] for c in mock_signal.call_args_list}
            assert signal.SIGTERM in signals_called
            assert signal.SIGINT in signals_called

    def test_start_resets_shutdown_requested(self, shutdown):
        """start() resets _shutdown_requested to False."""
        shutdown._shutdown_requested = True
        shutdown.start()
        assert shutdown.shutdown_requested is False


# ---------------------------------------------------------------------------
# Test: stop()
# ---------------------------------------------------------------------------


class TestStop:
    def test_stop_sets_running_false(self, shutdown):
        """stop() sets _running to False."""
        shutdown.start()
        shutdown.stop()
        assert shutdown.is_running() is False
        assert shutdown.running is False

    def test_stop_logs_message(self, shutdown):
        """stop() logs 'Shutting down...'."""
        shutdown.start()
        with patch("worker.graceful_shutdown.logger") as mock_logger:
            shutdown.stop()
            mock_logger.info.assert_called_once_with("Shutting down...")


# ---------------------------------------------------------------------------
# Test: request_shutdown()
# ---------------------------------------------------------------------------


class TestRequestShutdown:
    def test_request_shutdown_sets_flag(self, shutdown):
        """request_shutdown() sets _shutdown_requested to True."""
        shutdown.request_shutdown()
        assert shutdown.shutdown_requested is True

    def test_request_shutdown_stops_running(self, shutdown):
        """request_shutdown() also sets _running to False."""
        shutdown.start()
        shutdown.request_shutdown()
        assert shutdown.is_running() is False

    def test_request_shutdown_logs_message(self, shutdown):
        """request_shutdown() logs the shutdown message."""
        with patch("worker.graceful_shutdown.logger") as mock_logger:
            shutdown.request_shutdown()
            mock_logger.info.assert_called_with("Shutting down...")


# ---------------------------------------------------------------------------
# Test: Signal handlers
# ---------------------------------------------------------------------------


class TestSignalHandlers:
    def test_sigterm_calls_request_shutdown(self, shutdown):
        """SIGTERM signal triggers request_shutdown()."""
        shutdown.start()
        assert shutdown.is_running() is True
        shutdown._signal_handler(signal.SIGTERM, None)
        assert shutdown.is_running() is False
        assert shutdown.shutdown_requested is True

    def test_sigint_calls_request_shutdown(self, shutdown):
        """SIGINT signal triggers request_shutdown()."""
        shutdown.start()
        assert shutdown.is_running() is True
        shutdown._signal_handler(signal.SIGINT, None)
        assert shutdown.is_running() is False
        assert shutdown.shutdown_requested is True

    def test_sigterm_logs_signal_name(self, shutdown):
        """SIGTERM handler logs the signal name."""
        shutdown.start()
        with patch("worker.graceful_shutdown.logger") as mock_logger:
            shutdown._signal_handler(signal.SIGTERM, None)
            log_calls = [c for c in mock_logger.info.call_args_list if "received" in str(c)]
            assert len(log_calls) >= 1
            assert "SIGTERM" in str(log_calls[0])


# ---------------------------------------------------------------------------
# Test: Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_context_manager_start_on_enter(self):
        """__enter__ calls start() and returns self."""
        with GracefulShutdown() as gs:
            assert gs.is_running() is True

    def test_context_manager_stop_on_exit(self):
        """__exit__ calls stop() and restores handlers."""
        with patch("worker.graceful_shutdown.signal.signal") as mock_signal:
            with GracefulShutdown() as gs:
                assert gs.is_running() is True
            mock_signal.assert_called()

    def test_context_manager_returns_self(self):
        """__enter__ returns the GracefulShutdown instance."""
        with GracefulShutdown() as gs:
            assert isinstance(gs, GracefulShutdown)

    def test_context_manager_restores_original_handlers(self):
        """__exit__ restores original signal handlers."""
        original_handler = signal.SIG_DFL
        with (
            patch("worker.graceful_shutdown.signal.signal", return_value=original_handler) as mock_signal,
            GracefulShutdown(),
        ):
            pass
        # signal.signal is called during start (2 calls) and restore (2 calls)
        assert mock_signal.call_count >= 4

    def test_context_manager_exception_doesnt_suppress(self):
        """__exit__ does not suppress exceptions."""
        with pytest.raises(ValueError):  # noqa: SIM117
            with GracefulShutdown():
                raise ValueError("test")


# ---------------------------------------------------------------------------
# Test: restore_handlers()
# ---------------------------------------------------------------------------


class TestRestoreHandlers:
    def test_restore_handlers_restores_all(self):
        """restore_handlers() restores all registered handlers."""
        gs = GracefulShutdown()
        gs.start()
        with patch("worker.graceful_shutdown.signal.signal") as mock_signal:
            gs.restore_handlers()
            assert mock_signal.call_count == 2
            signals_restored = {c[0][0] for c in mock_signal.call_args_list}
            assert signal.SIGTERM in signals_restored
            assert signal.SIGINT in signals_restored

    def test_restore_handlers_clears_registry(self):
        """restore_handlers() clears the _original_handlers dict."""
        gs = GracefulShutdown()
        gs.start()
        gs.restore_handlers()
        assert gs._original_handlers == {}


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_stop_without_start(self, shutdown):
        """stop() works even if start() was never called."""
        shutdown.stop()
        assert shutdown.is_running() is False

    def test_request_shutdown_without_start(self, shutdown):
        """request_shutdown() works even if start() was never called."""
        shutdown.request_shutdown()
        assert shutdown.shutdown_requested is True

    def test_multiple_start_calls(self, shutdown):
        """Multiple start() calls are safe — resets state."""
        shutdown.start()
        shutdown.stop()
        shutdown.start()
        assert shutdown.is_running() is True
        assert shutdown.shutdown_requested is False

    def test_is_running_after_request_then_stop(self, shutdown):
        """is_running() correctly reflects state transitions."""
        shutdown.start()
        assert shutdown.is_running() is True
        shutdown.request_shutdown()
        assert shutdown.is_running() is False
        # After stop, request_shutdown still returns True
        assert shutdown.shutdown_requested is True
