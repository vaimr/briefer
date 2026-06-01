"""Duplicate task prevention via in-memory tracked set with TTL support.

Provides ``TaskTracker`` — a thread-safe class that records seen task IDs
and prevents re-processing of duplicate tasks.  Uses a dict-backed store
so that each task_id can optionally carry a timestamp for TTL-based cleanup.
"""

from __future__ import annotations

import threading
import time


class TaskTracker:
    """Track processed task IDs and prevent duplicate handling.

    Internally uses a ``dict[str, float]`` mapping ``task_id -> timestamp``
    so that ``cleanup_old_tasks()`` can evict entries older than a given
    threshold.  All public methods are protected by a ``threading.Lock``.

    Attributes:
        _seen: Mapping of task_id to its insertion timestamp (epoch seconds).
        _lock: Threading lock for thread-safe access.
    """

    def __init__(self) -> None:
        """Initialise an empty tracker with a fresh lock."""
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────

    def is_duplicate(self, task_id: str) -> bool:
        """Return ``True`` if *task_id* has already been recorded.

        If the task is new it is immediately recorded as seen.

        Args:
            task_id: Unique task identifier (e.g. UUID string).

        Returns:
            ``True`` if the task was already tracked (duplicate),
            ``False`` if the task was new and has just been recorded.
        """
        with self._lock:
            if task_id in self._seen:
                return True
            self._seen[task_id] = time.time()
            return False

    def mark_complete(self, task_id: str) -> None:
        """Record *task_id* as completed (add to seen set).

        Idempotent — calling this multiple times with the same *task_id*
        has no additional effect.

        Args:
            task_id: Unique task identifier.
        """
        with self._lock:
            self._seen[task_id] = time.time()

    def clear(self, task_id: str) -> None:
        """Remove *task_id* from the seen set.

        Idempotent — does nothing if *task_id* is not present.

        Args:
            task_id: Unique task identifier.
        """
        with self._lock:
            self._seen.pop(task_id, None)

    def cleanup_old_tasks(self, max_age_seconds: int = 3600) -> None:
        """Remove entries older than *max_age_seconds*.

        Iterates over a snapshot of keys to avoid mutation during iteration
        and removes any entry whose timestamp is older than the threshold.

        Args:
            max_age_seconds: Maximum age in seconds before eviction.
        """
        cutoff = time.time() - max_age_seconds
        with self._lock:
            old_keys = [
                tid for tid, ts in self._seen.items() if ts < cutoff
            ]
            for tid in old_keys:
                del self._seen[tid]

    def get_seen_count(self) -> int:
        """Return the number of currently tracked task IDs.

        Returns:
            Integer count of tracked tasks.
        """
        with self._lock:
            return len(self._seen)
