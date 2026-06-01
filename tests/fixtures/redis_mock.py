"""Mock Redis client for testing.

Provides a fake Redis client that mimics the interface of redis.Redis
used by bot and worker modules (rpush, blpop, publish, pubsub, ping).
"""

from unittest.mock import MagicMock, Mock


class FakeRedisPubSub:
    """Fake Redis pub/sub that yields messages from a queue."""

    def __init__(self):
        self._messages: list[str] = []
        self._subscribed_channels: list[str] = []
        self._listener_called = False

    def subscribe(self, *channels: str) -> None:
        """Subscribe to channels."""
        self._subscribed_channels.extend(channels)

    def listen(self):
        """Yield messages until the queue is exhausted."""
        while self._messages:
            data = self._messages.pop(0)
            yield {"type": "message", "data": data.encode()}
        # Yield a sentinel to signal no more messages
        yield {"type": "message", "data": "__NO_MORE__"}

    def put_message(self, data: str) -> None:
        """Add a message to the pub/sub queue."""
        self._messages.append(data)

    def unsubscribe(self, *channels: str) -> None:
        """Unsubscribe from channels."""
        for ch in channels:
            if ch in self._subscribed_channels:
                self._subscribed_channels.remove(ch)

    def psubscribe(self, *args, **kwargs) -> None:
        """No-op for pattern subscribe."""

    def punsubscribe(self, *args, **kwargs) -> None:
        """No-op for pattern unsubscribe."""

    def get_message(self, **kwargs):
        """Return next message or None."""
        if self._messages:
            data = self._messages.pop(0)
            return {"type": "message", "data": data.encode()}
        return None

    def close(self) -> None:
        """Close the pub/sub connection."""
        self._messages.clear()


class FakeRedis:
    """Fake Redis client for testing.

    Mimics redis.Redis interface for:
    - rpush / blpop (queue operations)
    - publish (pub/sub publishing)
    - pubsub (pub/sub creation)
    - ping (connectivity check)
    """

    def __init__(self, host: str = "redis", port: int = 6379, decode_responses: bool = False):
        self.host = host
        self.port = port
        self.decode_responses = decode_responses
        self._queues: dict[str, list[str]] = {}
        self._pubsub = FakeRedisPubSub()
        self._published: list[tuple[str, str]] = []

    def rpush(self, key: str, value: str) -> int:
        """Push value to the right of a list queue."""
        if key not in self._queues:
            self._queues[key] = []
        self._queues[key].append(value)
        return len(self._queues[key])

    def blpop(self, keys: str | list[str], timeout: int = 0) -> tuple[str, str] | None:
        """Pop value from the left of the first non-empty queue.

        Returns (queue_name, value) or (None, None) on timeout.
        """
        key_list = [keys] if isinstance(keys, str) else keys
        for key in key_list:
            if key in self._queues and self._queues[key]:
                return (key, self._queues[key].pop(0))
        return (None, None)

    def publish(self, channel: str, message: str) -> int:
        """Publish a message to a pub/sub channel."""
        self._published.append((channel, message))
        self._pubsub.put_message(message)
        return 1

    def pubsub(self) -> FakeRedisPubSub:
        """Return the fake pub/sub instance."""
        return self._pubsub

    def ping(self) -> bool:
        """Always returns True (Redis is 'up')."""
        return True

    def get_published_messages(self) -> list[tuple[str, str]]:
        """Return all published messages."""
        return list(self._published)

    def get_queue(self, key: str) -> list[str]:
        """Return queue contents."""
        return list(self._queues.get(key, []))

    def close(self) -> None:
        """Close the Redis connection."""
        self._queues.clear()
        self._published.clear()
        self._pubsub.close()


def mock_redis_client(host: str = "redis", port: int = 6379):
    """Factory fixture to create a FakeRedis client.

    Example:
        redis = mock_redis_client()
        redis.rpush("transcription_queue", "room1|/data/audio.wav")
        assert redis.get_queue("transcription_queue") == ["room1|/data/audio.wav"]
    """
    return FakeRedis(host=host, port=port)
