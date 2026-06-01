"""Result publisher — publishes transcription results to Redis pub/sub."""

import json
import logging
from datetime import datetime
from pathlib import Path

import redis

logger = logging.getLogger(__name__)


class ResultPublisher:
    """Publish transcription results to a Redis pub/sub channel.

    Attributes:
        CHANNEL: Redis channel name for result messages.
    """

    CHANNEL = "task_results"

    def __init__(self, redis_host: str, redis_port: int) -> None:
        """Initialize the publisher with Redis connection parameters.

        Args:
            redis_host: Redis server hostname.
            redis_port: Redis server port.
        """
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
        )

    def publish_result(
        self,
        task_id: str,
        transcription: dict,
        pdf_path: Path,
    ) -> None:
        """Publish a transcription result to the Redis channel.

        Args:
            task_id: Unique task identifier. Must not be empty.
            transcription: Dict with at least a ``"text"`` key; optional ``"summary"``.
            pdf_path: Path to the generated PDF file. Must exist.

        Raises:
            ValueError: If ``task_id`` is empty or ``transcription`` lacks ``"text"``.
            FileNotFoundError: If ``pdf_path`` does not exist.
        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id is required")

        if "text" not in transcription:
            raise ValueError("transcription must contain 'text' key")

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        message = {
            "task_id": task_id,
            "transcription": transcription["text"],
            "summary": transcription.get("summary", ""),
            "pdf_path": str(pdf_path),
            "timestamp": datetime.now().isoformat(),
        }

        self.redis.publish(self.CHANNEL, json.dumps(message))
        logger.info("Published result for task %s", task_id)
