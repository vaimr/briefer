"""Audio download and validation for Matrix bot.

Handles downloading audio messages from Matrix, validating file format
and constraints, and pushing tasks to the Redis transcription queue.
"""

import hashlib
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .config import BotConfig
from .exceptions import TaskQueueError

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS = {".wav", ".mp3", ".flac"}
MIN_DURATION = 3  # seconds
MAX_DURATION = 30 * 60  # 30 minutes in seconds
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB in bytes


class AudioDownloader:
    """Download, validate, and queue audio files from Matrix.

    Given: a BotConfig and data_dir
    When: audio messages arrive from Matrix
    Then: files are downloaded, validated, and pushed to Redis queue
    """

    SUPPORTED_FORMATS = SUPPORTED_FORMATS
    MIN_DURATION = MIN_DURATION
    MAX_DURATION = MAX_DURATION
    MAX_FILE_SIZE = MAX_FILE_SIZE

    def __init__(self, config: BotConfig, data_dir: str = "/data") -> None:
        """Initialize AudioDownloader.

        Creates the data directory if it does not exist.

        Args:
            config: Bot configuration instance.
            data_dir: Base directory for downloaded audio files.
        """
        self.config = config
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "AudioDownloader initialized: data_dir=%s", self.data_dir,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def download_audio(
        self,
        client,
        event,
    ) -> Path:
        """Download audio file from a Matrix event.

        Given: a Matrix client and an audio event with an URL
        When: the event contains downloadable media
        Then: the file is saved to data_dir/{message_id}.{ext}
        And: the Path to the saved file is returned

        Args:
            client: Matrix AsyncClient (or compatible) instance.
            event: Matrix audio event with ``url`` and ``message_id``.

        Returns:
            Path to the downloaded file.

        Raises:
            ValueError: If the event lacks required attributes.
        """
        url = _get_event_url(event)
        message_id = _get_event_message_id(event)

        if not url:
            raise ValueError("Event has no download URL")
        if not message_id:
            raise ValueError("Event has no message_id")

        ext = _extract_extension(event, url)
        file_path = self.data_dir / f"{message_id}{ext}"

        # Download the file
        response = await client.download(url)
        file_path.write_bytes(response.body)

        file_size = file_path.stat().st_size
        logger.info(
            "Downloaded audio: %s (%d bytes)",
            file_path,
            file_size,
        )

        return file_path

    def validate_audio(self, file_path: Path) -> bool:
        """Validate an audio file against format, size, and duration rules.

        Given: a path to an audio file
        When: the file exists and is a supported format
        And: its size is within limits
        And: its duration is within limits
        Then: return True
        Otherwise: return False and log a warning

        Args:
            file_path: Path to the audio file to validate.

        Returns:
            True if the file passes all validation checks.
        """
        path = Path(file_path)

        # Check file exists
        if not path.is_file():
            logger.warning("File does not exist: %s", path)
            return False

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            logger.warning(
                "File too large: %s (%d bytes > %d bytes)",
                path,
                file_size,
                self.MAX_FILE_SIZE,
            )
            return False

        # Check supported format
        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            logger.warning(
                "Unsupported format: %s (suffix=%s)",
                path,
                suffix,
            )
            return False

        # Check duration via ffprobe
        duration = self._get_duration(path)
        if duration is None:
            logger.warning(
                "Could not determine duration for: %s",
                path,
            )
            return False

        if duration < self.MIN_DURATION:
            logger.warning(
                "File too short: %s (%.1fs < %ds)",
                path,
                duration,
                self.MIN_DURATION,
            )
            return False

        if duration > self.MAX_DURATION:
            logger.warning(
                "File too long: %s (%.1fs > %ds)",
                path,
                duration,
                self.MAX_DURATION,
            )
            return False

        logger.info(
            "Audio validated: %s (format=%s, duration=%.1fs, size=%d)",
            path,
            suffix,
            duration,
            file_size,
        )
        return True

    def send_to_queue(
        self,
        redis_conn: "Redis",
        file_path: Path,
    ) -> str:
        """Push a transcription task to the Redis queue.

        Given: a Redis connection and a validated audio file path
        When: the file path contains room_id and message_id
        Then: rpush is called on "transcription_queue" with key
              "{room_id}:{message_id}"
        And: the key string is returned

        Args:
            redis_conn: Redis client instance.
            file_path: Path to the validated audio file.

        Returns:
            The Redis key used for the queue entry.

        Raises:
            TaskQueueError: If the Redis operation fails.
        """
        room_id = file_path.parent.name
        message_id = file_path.stem
        key = f"{room_id}:{message_id}"

        try:
            redis_conn.rpush("transcription_queue", key)
            logger.info("Pushed to queue: %s -> %s", key, file_path)
        except Exception as exc:
            logger.error("Failed to push to queue: %s", exc)
            raise TaskQueueError(f"Failed to push {key} to queue: {exc}") from exc

        return key

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_duration(self, file_path: Path) -> float | None:
        """Get audio duration in seconds using ffprobe.

        Given: a path to an audio file
        When: ffprobe is available and can read the file
        Then: return duration as float
        Otherwise: return None

        Args:
            file_path: Path to the audio file.

        Returns:
            Duration in seconds, or None if unavailable.
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(
                    "ffprobe returned non-zero for %s: %s",
                    file_path,
                    result.stderr.strip(),
                )
                return None

            duration_str = result.stdout.strip()
            if not duration_str:
                logger.warning("ffprobe returned empty duration for %s", file_path)
                return None

            return float(duration_str)

        except FileNotFoundError:
            logger.warning("ffprobe not found in PATH")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("ffprobe timed out for %s", file_path)
            return None
        except ValueError as exc:
            logger.warning(
                "Could not parse ffprobe output for %s: %s",
                file_path,
                exc,
            )
            return None


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


def _get_event_url(event) -> str | None:
    """Extract download URL from a Matrix event.

    Args:
        event: Matrix event object.

    Returns:
        URL string or None.
    """
    # nio RoomMessageAudio / RoomMessageFile expose .url
    url = getattr(event, "url", None)
    if url:
        return url

    # Fallback: content.body may contain the URL
    content = getattr(event, "content", None)
    if content is not None:
        body = getattr(content, "body", None)
        if body and isinstance(body, str) and body.startswith(("http://", "https://")):
            return body
        if isinstance(body, str) and body.startswith("mxc://"):
            return body

    return None


def _get_event_message_id(event) -> str | None:
    """Extract a safe file-id from a Matrix event.

    Uses SHA256 of event_id to avoid filesystem-unsafe characters.

    Args:
        event: Matrix event object.

    Returns:
        Safe 16-char hex string or None.
    """
    raw = event.source.get("event_id") if hasattr(event, "source") else None
    return hashlib.sha256(raw.encode()).hexdigest()[:16] if raw else None


def _extract_extension(event, url: str) -> str:
    """Determine file extension from event or URL.

    Priority:
    1. original_filename attribute on event
    2. URL path extension
    3. Default .wav

    Args:
        event: Matrix event object.
        url: Download URL.

    Returns:
        File extension string (e.g. ".wav").
    """
    # Check original_filename first
    original_filename = getattr(event, "original_filename", None)
    if original_filename:
        _, ext = os.path.splitext(original_filename)
        if ext:
            return ext.lower()

    # Extract from URL
    url_path = url.split("?")[0]  # strip query params
    _, ext = os.path.splitext(url_path)
    if ext:
        return ext.lower()

    # Default
    return ".wav"
