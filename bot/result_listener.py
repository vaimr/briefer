"""Redis pub/sub listener for receiving transcription results from workers."""

import json
import logging
import signal

logger = logging.getLogger(__name__)


class ResultListener:
    """Listens to Redis pub/sub channel ``task_results`` and invokes a callback.

    The listener runs in the caller's thread. It processes one message at a
    time, logging errors without stopping the loop.

    Attributes:
        redis_host: Redis server hostname or IP.
        redis_port: Redis server port.
        _running: Internal flag controlling the main loop (set ``False`` to stop).
    """

    CHANNEL = "task_results"
    CLEANUP_CHANNEL = "task_cleanup"

    def __init__(self, redis_host: str, redis_port: int) -> None:
        """Create a listener (does not connect yet).

        Args:
            redis_host: Redis server hostname or IP.
            redis_port: Redis server port.
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self._running = False

    def listen(self, callback) -> None:  # noqa: D401
        """Start listening on the Redis pub/sub channel.

        Creates a Redis client, subscribes to ``CHANNEL``, and calls
        *callback* with the parsed JSON payload for every message received.

        Args:
            callback: A callable accepting a single dict argument (the parsed
                      JSON payload).

        Raises:
            ConnectionError: If the Redis server is unreachable.
        """
        import redis

        self._running = True

        def _handle_signal(signum: int, frame) -> None:
            self._running = False

        try:
            signal.signal(signal.SIGTERM, _handle_signal)
            signal.signal(signal.SIGINT, _handle_signal)
        except ValueError:
            # signal.signal() only works in the main thread.
            # This is expected when the listener runs in a background thread.
            pass

        r = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            decode_responses=True,
        )
        pubsub = r.pubsub()
        pubsub.subscribe(self.CHANNEL)

        try:
            while self._running:
                message = pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                    except json.JSONDecodeError as exc:
                        logger.error("JSON parse error: %s", exc)
                        continue

                    if "task_id" not in data:
                        logger.error("Message missing task_id: %s", message["data"])
                        continue

                    try:
                        callback(data)
                    except Exception as exc:
                        logger.error("Callback error: %s", exc)
        finally:
            pubsub.unsubscribe(self.CHANNEL)
            pubsub.close()

    @staticmethod
    def publish_cleanup(redis_host: str, redis_port: int, task_id: str) -> None:
        """Publish a cleanup request for a completed task.

        Args:
            redis_host: Redis server hostname.
            redis_port: Redis server port.
            task_id: Task ID to clean up.
        """
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        r.publish(ResultListener.CLEANUP_CHANNEL, json.dumps({"task_id": task_id}))
        logger.info("Published cleanup for task %s", task_id)
