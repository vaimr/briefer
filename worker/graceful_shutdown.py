"""Graceful shutdown management for worker and bot processes."""

import contextlib
import logging
import signal

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Manages graceful shutdown of worker/bot processes.

    Handles SIGTERM and SIGINT signals, tracks running state,
    and provides context manager support for structured lifecycle.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._shutdown_requested: bool = False
        self._original_handlers: dict[int, signal.Handler] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the graceful shutdown manager.

        Sets ``_running`` to ``True`` and registers SIGTERM/SIGINT
        handlers that call :meth:`request_shutdown`.
        """
        self._running = True
        self._shutdown_requested = False
        self._original_handlers[signal.SIGTERM] = signal.signal(
            signal.SIGTERM, self._signal_handler
        )
        self._original_handlers[signal.SIGINT] = signal.signal(
            signal.SIGINT, self._signal_handler
        )
        logger.info("GracefulShutdown started")

    def stop(self) -> None:
        """Stop the graceful shutdown manager.

        Sets ``_running`` to ``False`` and logs a shutdown message.
        """
        self._running = False
        logger.info("Shutting down...")

    def is_running(self) -> bool:
        """Return ``True`` if the process is still running."""
        return self._running

    def request_shutdown(self) -> None:
        """Request a graceful shutdown.

        Sets ``_shutdown_requested`` to ``True`` and stops the process.
        """
        self._shutdown_requested = True
        self.stop()

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Signal handler that triggers graceful shutdown."""
        sig_name = signal.Signals(signum).name
        logger.info("Signal %s (%d) received, requesting graceful shutdown...", sig_name, signum)
        self.request_shutdown()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "GracefulShutdown":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.stop()
        self.restore_handlers()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def restore_handlers(self) -> None:
        """Restore original signal handlers."""
        for sig, handler in self._original_handlers.items():
            with contextlib.suppress(OSError, ValueError):
                signal.signal(sig, handler)  # type: ignore[arg-type]
        self._original_handlers.clear()

    # ------------------------------------------------------------------
    # Properties (for convenience)
    # ------------------------------------------------------------------

    @property
    def shutdown_requested(self) -> bool:
        """Return ``True`` if shutdown has been requested."""
        return self._shutdown_requested

    @property
    def running(self) -> bool:
        """Return ``True`` if the process is running."""
        return self._running
