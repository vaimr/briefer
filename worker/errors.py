"""Error handling and logging for the worker pipeline.

Provides ``TaskError`` data class and ``handle_error()`` function
that implement the retry → DLQ pattern with JSON-structured logging.
"""

import json
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskError:
    """Represents a retriable task error.

    Attributes:
        task_id: Unique identifier for the task that failed.
        error_type: Name of the exception class.
        message: Human-readable error message.
        retry_count: Number of retries attempted so far.
        traceback: Optional full traceback string.
    """

    task_id: str
    error_type: str
    message: str
    retry_count: int = 0
    traceback: str = field(default_factory=str)

    def __str__(self) -> str:
        return (
            f"TaskError(task_id={self.task_id!r}, "
            f"error_type={self.error_type!r}, "
            f"message={self.message!r}, "
            f"retry_count={self.retry_count})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "task_id": self.task_id,
            "error_type": self.error_type,
            "message": self.message,
            "retry_count": self.retry_count,
            "traceback": self.traceback or None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_exception(cls, task_id: str, exc: BaseException) -> "TaskError":
        """Create a TaskError from a plain exception."""
        tb = traceback.format_exc()
        return cls(
            task_id=task_id,
            error_type=type(exc).__name__,
            message=str(exc),
            traceback=tb,
        )


def _log_json(level: int, msg: str, extra: dict[str, Any] | None = None) -> None:
    """Log a JSON-structured message.

    Args:
        level: Logging level (e.g. logging.ERROR).
        msg: Human-readable message.
        extra: Additional fields to include in the JSON payload.
    """
    payload = {"message": msg, **(extra or {})}
    json_str = json.dumps(payload, default=str, ensure_ascii=False)
    logger.log(level, json_str)


def handle_error(
    task_id: str,
    error: BaseException | TaskError,
    max_retries: int,
) -> bool:
    """Handle a task error with retry logic and JSON logging.

    Implements the retry → dead-letter queue (DLQ) pattern:
    - If ``retry_count < max_retries`` → log, increment retry, return True (retry)
    - If ``retry_count >= max_retries`` → log as fatal, return False (DLQ)

    Args:
        task_id: Unique task identifier.
        error: The exception or TaskError that occurred.
        max_retries: Maximum number of retry attempts allowed.

    Returns:
        True if the task should be retried, False if it should be sent to DLQ.

    Raises:
        ValueError: If ``error`` is None or ``max_retries < 0``.
    """
    if error is None:
        raise ValueError("error cannot be None")
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")

    if isinstance(error, TaskError):
        task_err = error
        # Check BEFORE increment: can we retry?
        if task_err.retry_count < max_retries:
            task_err.retry_count += 1
            _log_json(
                logging.WARNING,
                f"Task {task_id} retry {task_err.retry_count}/{max_retries}",
                extra={
                    "task_id": task_id,
                    "error_type": task_err.error_type,
                    "message": task_err.message,
                    "retry_count": task_err.retry_count,
                    "max_retries": max_retries,
                    "action": "retry",
                },
            )
            return True
        else:
            _log_json(
                logging.ERROR,
                f"Task {task_id} sent to DLQ",
                extra={
                    "task_id": task_id,
                    "error_type": task_err.error_type,
                    "message": task_err.message,
                    "retry_count": task_err.retry_count,
                    "max_retries": max_retries,
                    "action": "dlq",
                },
            )
            return False
    else:
        # Fresh exception — first failure
        task_err = TaskError.from_exception(task_id, error)
        task_err.retry_count = 1

        if task_err.retry_count <= max_retries and max_retries > 0:
            _log_json(
                logging.WARNING,
                f"Task {task_id} retry 1/{max_retries}",
                extra={
                    "task_id": task_id,
                    "error_type": task_err.error_type,
                    "message": task_err.message,
                    "retry_count": task_err.retry_count,
                    "max_retries": max_retries,
                    "action": "retry",
                },
            )
            return True
        else:
            _log_json(
                logging.ERROR,
                f"Task {task_id} sent to DLQ (first failure)",
                extra={
                    "task_id": task_id,
                    "error_type": task_err.error_type,
                    "message": task_err.message,
                    "retry_count": task_err.retry_count,
                    "max_retries": max_retries,
                    "action": "dlq",
                },
            )
            return False
