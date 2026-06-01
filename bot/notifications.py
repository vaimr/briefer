"""Matrix status notifications for the Briefer bot."""

import logging

from nio.responses import RoomSendError

from bot.client import MatrixClientError

logger = logging.getLogger(__name__)

STATUS_EMOJIS: dict[str, str] = {
    "processing": "\u23f3",
    "done": "\u2705",
    "error": "\u274c",
}

MAX_MESSAGE_LENGTH: int = 4000


def send_status(
    client,
    room_id: str,
    status: str,
    message: str,
) -> None:
    """Send a status update to a Matrix room.

    Given: a valid Matrix client, non-empty room_id, and a known status
    When: the message is sent
    Then: a formatted notice is delivered to the room
    And: the formatted message is logged
    And: Matrix errors are caught and logged without propagating
    And: any other unexpected errors are caught and logged without propagating

    Args:
        client: Matrix AsyncClient instance (or mock).
        room_id: Matrix room identifier (must not be empty).
        status: One of ``processing``, ``done``, ``error``.
        message: Status message text.

    Raises:
        ValueError: If ``room_id`` is empty or ``status`` is unknown.
    """
    if not room_id or not room_id.strip():
        raise ValueError("room_id must not be empty")

    if status not in STATUS_EMOJIS:
        raise ValueError(
            f"Unknown status '{status}'; expected one of {sorted(STATUS_EMOJIS)}"
        )

    emoji = STATUS_EMOJIS[status]
    truncated = message[:MAX_MESSAGE_LENGTH]
    formatted = f"{emoji} {truncated}"

    try:
        response = client.room_send(
            room_id,
            "m.room.message",
            {"msgtype": "m.notice", "body": formatted},
        )
        if isinstance(response, RoomSendError):
            logger.error(
                "Failed to send status notification: room=%s, status=%s, error=%s",
                room_id,
                status,
                response,
            )
            return
        logger.info(
            "Status notification sent: room=%s, status=%s, message=%s",
            room_id,
            status,
            truncated,
        )
    except MatrixClientError as exc:
        logger.error(
            "Matrix client error while sending status: room=%s, status=%s, error=%s",
            room_id,
            status,
            exc,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error sending status: room=%s, status=%s, error=%s",
            room_id,
            status,
            exc,
        )
