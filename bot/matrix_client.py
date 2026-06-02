"""Matrix client wrapper с callback-ами для аудио сообщений."""

import hashlib
import logging
import os
from pathlib import Path

from nio import (
    AsyncClient,
    RoomMessageAudio,
    RoomMessageFile,
    UploadResponse,
)

from .config import BotConfig
from .metrics import BOT_MESSAGES_PROCESSED, BOT_MESSAGES_RECEIVED

_matrix_logger = logging.getLogger("bot")


def load_help_text(help_text_file: str) -> str:
    """Load help text from file.

    Given: a help_text_file path
    When: the file exists
    Then: return its content as UTF-8 string
    When: the file does not exist
    Then: return default help message and log warning
    """
    path = Path(help_text_file)
    if path.exists():
        return path.read_text(encoding="utf-8")
    _matrix_logger.warning(
        "Help text file not found: %s, using default", help_text_file,
    )
    return (
        "Я не отвечаю на текстовые сообщения.\n"
        "Отправьте аудиофайл — я верну расшифровку (MD+PDF), резюме (MD+PDF) и предупреждения по рискам."
    )


async def create_client(config: BotConfig) -> AsyncClient:
    """Create and authenticate a Matrix client.

    Given: a BotConfig with MATRIX_HOMESERVER and MATRIX_USER
    When: MATRIX_ACCESS_TOKEN is set
    Then: attach the token directly
    When: MATRIX_PASSWORD is set (no token)
    Then: perform login to obtain a token
    """
    client = AsyncClient(config.MATRIX_HOMESERVER, config.MATRIX_USER)
    if config.MATRIX_ACCESS_TOKEN:
        client.access_token = config.MATRIX_ACCESS_TOKEN
        _matrix_logger.info("Connected to Matrix using access token: %s", config.MATRIX_HOMESERVER)
    elif config.MATRIX_PASSWORD:
        await client.login(password=config.MATRIX_PASSWORD)
        _matrix_logger.info("Logged in to Matrix: %s", config.MATRIX_USER)
    else:
        _matrix_logger.error("No authentication configured (no access token or password)")

    try:
        sync_resp = await client.sync(timeout=5000)
        _matrix_logger.info("Sync response: batch_id=%s", getattr(sync_resp, 'batch_token', 'N/A'))
        if hasattr(sync_resp, 'rooms') and sync_resp.rooms:
            for room_type in ("join", "invite", "leave"):
                room_dict = getattr(sync_resp.rooms, room_type, {})
                if room_dict:
                    for room_id, room in room_dict.items():
                        _matrix_logger.info("Room: %s [%s] name=%s", room_id, room_type, getattr(room, 'name', 'N/A'))
    except Exception as e:
        _matrix_logger.error("Error listing rooms: %s", e)

    return client


async def handle_audio_message(
    client: AsyncClient,
    room_id: str,
    event,
    download_dir: str,
    queue_push,
) -> str:
    """Обработка аудио сообщения: скачивание и отправка в очередь.

    Returns:
        filename: путь к скачанному файлу
    """
    BOT_MESSAGES_RECEIVED.labels(type="audio").inc()

    resp = await client.download(event.url)
    raw_filename = event.source.get("content", {}).get("filename") or event.body or "audio"
    _, ext = os.path.splitext(raw_filename)
    if not ext:
        ext = ".wav"
    msg_id = hashlib.sha256(event.event_id.encode()).hexdigest()[:16]
    filename = f"{download_dir}/{msg_id}{ext}"

    # Ensure download directory exists
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    with open(filename, "wb") as f:
        f.write(resp.body)

    file_size = os.path.getsize(filename)
    logger.info("Downloaded: %s (%d bytes), filename=%s, url=%s", filename, file_size, raw_filename, event.url)
    # Проверка что файл не пустой и не HTML
    with open(filename, "rb") as f:
        header = f.read(20)
        logger.info("File header: %r", header)

    event_id = getattr(event, "event_id", None)
    queue_push(f"{room_id}|{filename}|{raw_filename}|{event_id}")
    BOT_MESSAGES_PROCESSED.labels(status="queued").inc()

    await client.room_send(
        room_id,
        "m.room.message",
        {"msgtype": "m.notice", "body": "Файл принят, идёт обработка..."},
    )

    return filename


async def handle_non_audio_message(
    client: AsyncClient,
    room_id: str,
    help_text: str = "",
):
    """Send help text when non-audio message is received.

    Given: a room_id and help_text
    When: a non-audio message arrives
    Then: send help_text as notice message to the room
    """
    BOT_MESSAGES_RECEIVED.labels(type="other").inc()
    await client.room_send(
        room_id,
        "m.room.message",
        {
            "msgtype": "m.notice",
            "body": help_text,
        },
    )


def get_audio_event_type(event) -> bool:
    """Проверка является ли событие аудио."""
    if isinstance(event, RoomMessageAudio):
        return True
    if isinstance(event, RoomMessageFile):
        content = event.source.get("content", {})
        mime = content.get("info", {}).get("mimetype", "")
        return mime.startswith("audio/")
    return False
