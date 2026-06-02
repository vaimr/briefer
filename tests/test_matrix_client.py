"""Tests for matrix_client module."""

import hashlib
import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from bot.matrix_client import (
    create_client,
    get_audio_event_type,
    handle_audio_message,
    handle_non_audio_message,
    load_help_text,
)

logger = logging.getLogger("test_matrix_client")


def _safe_msg_id(event_id: str) -> str:
    """SHA256 hash of event_id (first 16 chars)."""
    return hashlib.sha256(event_id.encode()).hexdigest()[:16]


class TestLoadHelpText:
    """Tests for load_help_text function."""

    def test_load_help_text_from_file(self, tmp_path: Path):
        """When help text file exists → return its content."""
        help_file = tmp_path / "help.txt"
        help_file.write_text("Custom help text", encoding="utf-8")

        result = load_help_text(str(help_file))

        assert result == "Custom help text"

    def test_load_help_text_default_when_file_missing(self):
        """When help text file does not exist → return default message."""
        result = load_help_text("/nonexistent/path/help.txt")

        assert "не отвечаю" in result
        assert "аудиофайл" in result
        assert "расшифровку" in result


class TestGetAudioEventType:
    """Tests for get_audio_event_type function."""

    def test_audio_event_returns_true(self):
        """When event is RoomMessageAudio → return True."""
        from nio import RoomMessageAudio

        event = MagicMock(spec=RoomMessageAudio)
        assert get_audio_event_type(event) is True

    def test_audio_mime_file_returns_true(self):
        """When event is RoomMessageFile with audio mime type → return True."""
        from nio import RoomMessageFile

        event = MagicMock(spec=RoomMessageFile)
        event.source = {"content": {"info": {"mimetype": "audio/ogg"}}}
        assert get_audio_event_type(event) is True

    def test_non_audio_mime_file_returns_false(self):
        """When event is RoomMessageFile with non-audio mime type → return False."""
        from nio import RoomMessageFile

        event = MagicMock(spec=RoomMessageFile)
        event.source = {"content": {"info": {"mimetype": "image/png"}}}
        assert get_audio_event_type(event) is False


class TestHandleAudioMessage:
    """Tests for handle_audio_message function.
    
    RoomMessageAudio has: event_id, url, body, source (dict with content).
    original_filename is in event.source["content"]["filename"].
    """

    @pytest.mark.asyncio
    async def test_handles_audio_message(self, tmp_path: Path):
        """When audio message received → download, queue, notify."""
        client = AsyncMock()
        client.download = AsyncMock(return_value=Mock(body=b"audio data"))

        event = Mock()
        event.url = "mxc://server/audio"
        event.event_id = "$msg1"
        event.source = {
            "content": {
                "filename": "test.ogg",
                "msgtype": "m.audio",
                "body": "test.ogg",
            }
        }

        download_dir = str(tmp_path / "input")
        os.makedirs(download_dir, exist_ok=True)
        queue_push = Mock()

        result = await handle_audio_message(
            client, "!room:server", event, download_dir, queue_push
        )

        client.download.assert_called_once_with("mxc://server/audio")
        expected_id = _safe_msg_id("$msg1")
        queue_push.assert_called_once_with("!room:server|{}/{}.ogg|test.ogg|$msg1".format(download_dir, expected_id))
        client.room_send.assert_called_once()
        assert "Файл принят" in client.room_send.call_args[0][2]["body"]
        assert result == "{}/{}.ogg".format(download_dir, expected_id)

    @pytest.mark.asyncio
    async def test_handles_audio_without_filename(self, tmp_path: Path):
        """When audio message has no filename → body without extension → .wav fallback."""
        client = AsyncMock()
        client.download = AsyncMock(return_value=Mock(body=b"audio data"))

        event = Mock()
        event.url = "mxc://server/audio"
        event.event_id = "$msg2"
        event.source = {"content": {"msgtype": "m.audio", "body": "my audio"}}
        event.body = "my audio"

        download_dir = str(tmp_path / "input2")
        os.makedirs(download_dir, exist_ok=True)
        queue_push = Mock()

        result = await handle_audio_message(
            client, "!room:server", event, download_dir, queue_push
        )

        expected_id = _safe_msg_id("$msg2")
        assert "{}/{}.wav".format(download_dir, expected_id) in result

    @pytest.mark.asyncio
    async def test_handles_audio_with_none_body(self, tmp_path: Path):
        """When audio message has no filename and no body → 'audio' default → .wav fallback."""
        client = AsyncMock()
        client.download = AsyncMock(return_value=Mock(body=b"audio data"))

        event = Mock()
        event.url = "mxc://server/audio"
        event.event_id = "$msg3"
        event.source = {"content": {"msgtype": "m.audio"}}
        event.body = None

        download_dir = str(tmp_path / "input3")
        os.makedirs(download_dir, exist_ok=True)
        queue_push = Mock()

        result = await handle_audio_message(
            client, "!room:server", event, download_dir, queue_push
        )

        expected_id = _safe_msg_id("$msg3")
        assert "{}/{}.wav".format(download_dir, expected_id) in result


class TestHandleNonAudioMessage:
    """Tests for handle_non_audio_message function."""

    @pytest.mark.asyncio
    async def test_sends_help_text(self):
        """When non-audio message received → send help text."""
        client = AsyncMock()
        help_text = "Help: send audio"

        await handle_non_audio_message(client, "!room:server", help_text)

        client.room_send.assert_called_once_with(
            "!room:server",
            "m.room.message",
            {"msgtype": "m.notice", "body": "Help: send audio"},
        )
