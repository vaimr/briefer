"""Unit tests for worker/task_tracker.py — Duplicate Task Prevention (T6.4)."""

import threading
import time

import pytest

from worker.task_tracker import TaskTracker

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tracker():
    """Return a fresh TaskTracker for each test."""
    return TaskTracker()


@pytest.fixture
def sample_task_id():
    """Return a deterministic UUID string."""
    return "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def second_task_id():
    """Return a different UUID string."""
    return "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


# ── is_duplicate tests ────────────────────────────────────────────────────

class TestIsDuplicate:
    def test_returns_false_for_new_task(self, tracker, sample_task_id):
        """A brand-new task_id should return False (not a duplicate)."""
        result = tracker.is_duplicate(sample_task_id)
        assert result is False

    def test_returns_true_for_seen_task(self, tracker, sample_task_id):
        """Calling is_duplicate twice with the same task_id should return
        False on first call and True on second."""
        tracker.is_duplicate(sample_task_id)
        assert tracker.is_duplicate(sample_task_id) is True

    def test_multiple_different_tasks(self, tracker, sample_task_id, second_task_id):
        """Different task IDs should all return False initially."""
        assert tracker.is_duplicate(sample_task_id) is False
        assert tracker.is_duplicate(second_task_id) is False
        # Both are now duplicates
        assert tracker.is_duplicate(sample_task_id) is True
        assert tracker.is_duplicate(second_task_id) is True

    def test_get_seen_count_after_is_duplicate(self, tracker, sample_task_id):
        """After is_duplicate a new task, count should be 1."""
        tracker.is_duplicate(sample_task_id)
        assert tracker.get_seen_count() == 1

    def test_get_seen_count_after_multiple_tasks(self, tracker, sample_task_id, second_task_id):
        """After is_duplicate two different tasks, count should be 2."""
        tracker.is_duplicate(sample_task_id)
        tracker.is_duplicate(second_task_id)
        assert tracker.get_seen_count() == 2


# ── mark_complete tests ───────────────────────────────────────────────────

class TestMarkComplete:
    def test_mark_complete_makes_task_duplicate(self, tracker, sample_task_id):
        """mark_complete should record the task so is_duplicate returns True."""
        tracker.mark_complete(sample_task_id)
        assert tracker.is_duplicate(sample_task_id) is True

    def test_mark_complete_is_idempotent(self, tracker, sample_task_id):
        """Calling mark_complete twice should not change behaviour."""
        tracker.mark_complete(sample_task_id)
        tracker.mark_complete(sample_task_id)
        count = tracker.get_seen_count()
        assert count == 1

    def test_mark_complete_without_prior_is_duplicate(self, tracker, sample_task_id):
        """mark_complete can be called directly without prior is_duplicate."""
        assert tracker.get_seen_count() == 0
        tracker.mark_complete(sample_task_id)
        assert tracker.get_seen_count() == 1


# ── clear tests ───────────────────────────────────────────────────────────

class TestClear:
    def test_clear_removes_from_seen(self, tracker, sample_task_id):
        """After clear, is_duplicate should return False again."""
        tracker.is_duplicate(sample_task_id)
        tracker.clear(sample_task_id)
        assert tracker.is_duplicate(sample_task_id) is False

    def test_clear_nonexistent_task_is_safe(self, tracker, sample_task_id):
        """clear on a task that was never tracked should not raise."""
        tracker.clear(sample_task_id)  # no exception
        assert tracker.get_seen_count() == 0

    def test_clear_preserves_other_tasks(self, tracker, sample_task_id, second_task_id):
        """Clearing one task should not affect another."""
        tracker.is_duplicate(sample_task_id)
        tracker.is_duplicate(second_task_id)
        tracker.clear(sample_task_id)
        assert tracker.get_seen_count() == 1
        assert tracker.is_duplicate(second_task_id) is True


# ── cleanup_old_tasks tests ──────────────────────────────────────────────

class TestCleanupOldTasks:
    def test_cleanup_removes_old_entries(self, tracker):
        """Entries older than max_age_seconds should be removed."""
        # Manually inject an old entry by accessing internal state
        tracker._seen["old-task"] = time.time() - 7200  # 2 hours ago
        tracker._seen["new-task"] = time.time()
        assert tracker.get_seen_count() == 2

        tracker.cleanup_old_tasks(max_age_seconds=3600)
        assert tracker.get_seen_count() == 1
        assert "old-task" not in tracker._seen
        assert "new-task" in tracker._seen

    def test_cleanup_with_zero_age_removes_all(self, tracker):
        """max_age_seconds=0 should remove everything."""
        tracker._seen["task-1"] = time.time() - 10
        tracker._seen["task-2"] = time.time() - 5
        tracker.cleanup_old_tasks(max_age_seconds=0)
        assert tracker.get_seen_count() == 0

    def test_cleanup_keeps_recent_entries(self, tracker):
        """Entries within the threshold should be kept."""
        tracker._seen["recent"] = time.time()
        tracker._seen["recent2"] = time.time() - 100
        tracker.cleanup_old_tasks(max_age_seconds=3600)
        assert tracker.get_seen_count() == 2


# ── Thread safety tests ───────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_is_duplicate(self, tracker):
        """Concurrent is_duplicate calls should not crash or lose entries."""
        num_threads = 10
        tasks_per_thread = 100
        barrier = threading.Barrier(num_threads)
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                barrier.wait(timeout=5)
                for i in range(tasks_per_thread):
                    tid = f"thread-{thread_id}-task-{i}"
                    tracker.is_duplicate(tid)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(tid,))
            for tid in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        assert tracker.get_seen_count() == num_threads * tasks_per_thread

    def test_concurrent_mark_complete_and_clear(self, tracker):
        """mark_complete and clear running concurrently should not crash."""
        barrier = threading.Barrier(4)
        errors: list[Exception] = []

        def marker(thread_id: int) -> None:
            try:
                barrier.wait(timeout=5)
                for i in range(200):
                    tracker.mark_complete(f"t{thread_id}-{i}")
            except Exception as exc:
                errors.append(exc)

        def clearer(thread_id: int) -> None:
            try:
                barrier.wait(timeout=5)
                for i in range(200):
                    tracker.clear(f"t{thread_id}-{i}")
            except Exception as exc:
                errors.append(exc)

        threads = []
        for i in range(2):
            threads.append(threading.Thread(target=marker, args=(i,)))
            threads.append(threading.Thread(target=clearer, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
