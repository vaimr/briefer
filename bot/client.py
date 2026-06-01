"""Matrix AsyncClient creation wrapper with authentication."""

import logging

from nio import AsyncClient
from redis import ConnectionError as RedisConnectionError

from bot.config import BotConfig

logger = logging.getLogger(__name__)


class MatrixClientError(Exception):
    """Raised when Matrix client authentication fails."""


async def create_client(config: BotConfig) -> AsyncClient:
    """Create and authenticate a Matrix AsyncClient.

    Authentication precedence:
    1. access_token (token auth) — if present, used directly.
    2. password — if access_token is absent but password is present,
       performs login to obtain a token.

    Args:
        config: Parsed bot settings containing Matrix credentials.

    Returns:
        Authenticated AsyncClient instance with user_id set.

    Raises:
        ValueError: If neither access_token nor password is provided.
        MatrixClientError: If password-based login fails.
    """
    client = AsyncClient(config.MATRIX_HOMESERVER, config.MATRIX_USER)

    if config.MATRIX_ACCESS_TOKEN:
        # Token auth takes precedence — attach it directly.
        client.access_token = config.MATRIX_ACCESS_TOKEN
        logger.info(
            "Matrix client authenticated with access_token for user %s",
            config.MATRIX_USER,
        )
    elif config.MATRIX_PASSWORD:
        # Password auth — perform login to obtain token + device.
        logger.info(
            "Matrix client authenticating with password for user %s",
            config.MATRIX_USER,
        )
        try:
            await client.login(
                password=config.MATRIX_PASSWORD,
                device_name="briefer-bot",
            )
        except Exception as exc:
            raise MatrixClientError(f"Matrix login failed: {exc}") from exc
        logger.info(
            "Matrix client authenticated with password for user %s",
            config.MATRIX_USER,
        )
    else:
        raise ValueError(
            "Matrix authentication requires either MATRIX_ACCESS_TOKEN or "
            "MATRIX_PASSWORD in config "
            f"(homeserver={config.MATRIX_HOMESERVER}, user={config.MATRIX_USER})"
        )

    logger.info(
        "Matrix client ready — user_id=%s",
        client.user_id,
    )
    return client


# ---------------------------------------------------------------------------
# Redis Queue Producer
# ---------------------------------------------------------------------------

from redis import Redis

QUEUE_NAME = "transcription_queue"


def enqueue_task(redis_conn: Redis, room_id: str, audio_path: str) -> str:
    """Push a transcription task onto the Redis queue.

    Given: a Redis connection, a non-empty room_id and audio_path
    When: the queue is reachable
    Then: the task is formatted as ``f"{room_id}|{audio_path}"``
          and appended via ``rpush`` to ``transcription_queue``
    And: the formatted task string is returned

    Args:
        redis_conn: Active Redis client instance.
        room_id: Matrix room identifier (must not be empty).
        audio_path: Absolute or relative path to the audio file (must not be empty).

    Returns:
        The formatted task string ``f"{room_id}|{audio_path}"``.

    Raises:
        ValueError: If ``room_id`` or ``audio_path`` is empty.
        ConnectionError: If the Redis server is unreachable.
    """
    if not room_id or not room_id.strip():
        raise ValueError("room_id must not be empty")
    if not audio_path or not audio_path.strip():
        raise ValueError("audio_path must not be empty")

    task = f"{room_id}|{audio_path}"

    try:
        redis_conn.rpush(QUEUE_NAME, task)
    except RedisConnectionError as exc:
        raise ConnectionError(f"Redis connection failed: {exc}") from exc

    logger.info(
        "Enqueued task: room_id=%s, audio_path=%s, task=%s",
        room_id,
        audio_path,
        task,
    )
    return task
