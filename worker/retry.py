"""Retry decorator with exponential backoff for transient errors."""

import functools
import logging
import time
from collections.abc import Callable

TRANSIENT_ERRORS: tuple[type[Exception], ...] = (ConnectionError, TimeoutError, OSError)

logger = logging.getLogger(__name__)


def retry(max_retries: int = 3, base_delay: float = 1.0) -> Callable:
    """Retry decorator with exponential backoff for transient errors.

    Retries the decorated function up to *max_retries* times when a transient
    error (ConnectionError, TimeoutError, OSError) is raised.  Permanent errors
    are re-raised immediately without retry.

    Back-off delay per attempt::

        delay = base_delay * (2 ** attempt)

    Args:
        max_retries: Maximum number of retry attempts (default 3).
        base_delay: Base delay in seconds for exponential back-off (default 1.0).

    Returns:
        A decorator that wraps *func* with retry logic.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except TRANSIENT_ERRORS as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "%s failed (attempt %d), retrying in %.1fs: %s",
                            func.__name__,
                            attempt + 1,
                            delay,
                            e,
                        )
                        time.sleep(delay)
                    else:
                        raise
                except Exception:
                    raise

            if last_exception is not None:
                raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
