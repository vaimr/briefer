"""Dead Letter Queue for failed transcription tasks.

Stores tasks that exhausted all retries in a Redis list
so they can be inspected, reprocessed, or discarded later.
"""

import json
import logging
from datetime import datetime

import redis

logger = logging.getLogger(__name__)


class DeadLetterQueue:
    """Redis-backed dead letter queue for failed tasks.

    Uses a Redis list channel to store JSON-encoded failure records.
    Automatically truncates the oldest entries when the queue exceeds
    ``MAX_SIZE``.

    Attributes:
        CHANNEL: Redis key used for the DLQ list.
        MAX_SIZE: Maximum number of entries before truncation.
    """

    CHANNEL = "dlq:transcription"
    MAX_SIZE = 10000

    def __init__(self, redis_client: redis.Redis) -> None:
        """Initialize the DLQ with a Redis connection.

        Args:
            redis_client: A connected :class:`redis.Redis` instance.

        Raises:
            ValueError: If ``redis_client`` is ``None``.
        """
        if redis_client is None:
            raise ValueError("redis_client cannot be None")
        self.redis = redis_client

    def add(self, task_id: str, error: Exception, tb: str) -> None:
        """Add a failed task record to the DLQ.

        Args:
            task_id: Unique identifier of the failed task.
            error: The exception that caused the failure.
            tb: Full traceback string.

        Raises:
            ValueError: If ``task_id`` is empty or ``error`` is ``None``.
        """
        if not task_id:
            raise ValueError("task_id is required")
        if error is None:
            raise ValueError("error is required")

        message = {
            "task_id": task_id,
            "error": str(error),
            "traceback": tb,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self.redis.rpush(self.CHANNEL, json.dumps(message))

            # Truncate oldest entries if queue is too large
            while self.redis.llen(self.CHANNEL) > self.MAX_SIZE:
                self.redis.lpop(self.CHANNEL)
        except redis.RedisError as exc:
            logger.error("Failed to add task %s to DLQ: %s", task_id, exc)

    def get_all(self) -> list[dict]:
        """Retrieve all records currently in the DLQ.

        Returns:
            A list of dicts, each containing
            ``task_id``, ``error``, ``traceback``, and ``timestamp``.
        """
        messages = self.redis.lrange(self.CHANNEL, 0, -1)
        return [json.loads(m) for m in messages]

    def remove(self, task_id: str) -> None:
        """Remove a specific task record from the DLQ.

        Args:
            task_id: The task identifier to remove.
        """
        messages = self.get_all()
        for msg in messages:
            if msg["task_id"] == task_id:
                serialized = json.dumps(msg)
                self.redis.lrem(self.CHANNEL, 1, serialized)
                break
