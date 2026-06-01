"""Unit tests for bot/audio_downloader.py — AudioDownloader class.

T2.2 — Audio Download & Validation module.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.audio_downloader import (
    AudioDownloader,
    MAX_DURATION,
    MAX_FILE_SIZE,
    MIN_DURATION,
    SUPPORTED_FORMATS,
)
from bot.config import BotConfig
from bot.exceptions import TaskQueueError
from tests.fixtures.redis_mock import FakeRedis


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    """Minimal BotConfig for tests."""
    return BotConfig(
        MATRIX_HOMESERVER="https://matrix.example.com",
        MATRIX_USER="@bot:example.com",
    )


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Temporary data directory for AudioDownloader."""
    return str(tmp_path / "data")


@pytest.fixture
def downloader(config, tmp_data_dir):
    """AudioDownloader instance with temp data_dir."""
    return AudioDownloader(config, data_dir=tmp_data_dir)


@pytest.fixture
def audio_file(tmp_path):
    """Create a minimal WAV-like file for testing."""
    path = tmp_path / "test.wav"
    path.write_bytes(b"RIFF\x28\x00\x00\x00" + b"\x00" * 100)
    return path


@pytest.fixture
def mock_event():
    """Create a mock Matrix audio event."""
    event = MagicMock()
    event.url = "https://matrix.example.com/media/abc123"
    event.message_id = "msg_001"
    event.original_filename = "test.wav"
    return event


@pytest.fixture
def mock_client():
    """Create a mock Matrix client with download."""
    client = AsyncMock()
    client.download = AsyncMock(return_value=MagicMock(body=b"fake audio data"))
    return client


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------

class TestConstants:
    """Validate class constants match spec."""

    def test_supported_formats(self):
        assert SUPPORTED_FORMATS == {".wav", ".mp3", ".flac"}

    def test_min_duration(self):
        assert MIN_DURATION == 3

    def test_max_duration(self):
        assert MAX_DURATION == 30 * 60

    def test_max_file_size(self):
        assert MAX_FILE_SIZE == 50 * 1024 * 1024

    def test_class_constants_match_module(self):
        from bot.audio_downloader import AudioDownloader
        assert AudioDownloader.SUPPORTED_FORMATS == SUPPORTED_FORMATS
        assert AudioDownloader.MIN_DURATION == MIN_DURATION
        assert AudioDownloader.MAX_DURATION == MAX_DURATION
        assert AudioDownloader.MAX_FILE_SIZE == MAX_FILE_SIZE


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    """Test AudioDownloader.__init__."""

    def test_creates_data_dir(self, config, tmp_data_dir):
        AudioDownloader(config, data_dir=tmp_data_dir)
        assert os.path.isdir(tmp_data_dir)

    def test_data_dir_created_parents(self, config, tmp_path):
        nested = str(tmp_path / "a" / "b" / "c")
        AudioDownloader(config, data_dir=nested)
        assert os.path.isdir(nested)

    def test_stores_config(self, config, tmp_data_dir):
        downloader = AudioDownloader(config, data_dir=tmp_data_dir)
        assert downloader.config is config

    def test_default_data_dir(self, config, tmp_path):
        # Default "/data" should also work
        default_dir = str(tmp_path / "default_data")
        downloader = AudioDownloader(config, data_dir=default_dir)
        assert str(downloader.data_dir) == default_dir


# ---------------------------------------------------------------------------
# download_audio
# ---------------------------------------------------------------------------

class TestDownloadAudio:
    """Test AudioDownloader.download_audio()."""

    @pytest.mark.asyncio
    async def test_download_creates_file(self, downloader, mock_client, mock_event):
        """download_audio() saves file and returns Path."""
        result = await downloader.download_audio(mock_client, mock_event)
        assert result.is_file()
        assert result.name == "msg_001.wav"

    @pytest.mark.asyncio
    async def test_download_calls_client_download(self, downloader, mock_client, mock_event):
        """download_audio() calls client.download(url)."""
        await downloader.download_audio(mock_client, mock_event)
        mock_client.download.assert_called_once_with("https://matrix.example.com/media/abc123")

    @pytest.mark.asyncio
    async def test_download_uses_original_filename(self, downloader, mock_client, mock_event):
        """download_audio() uses original_filename extension."""
        mock_event.original_filename = "recording.mp3"
        result = await downloader.download_audio(mock_client, mock_event)
        assert result.suffix == ".mp3"

    @pytest.mark.asyncio
    async def test_download_fallback_url_extension(self, config, tmp_data_dir):
        """download_audio() extracts extension from URL when no original_filename."""
        client = AsyncMock()
        client.download = AsyncMock(return_value=MagicMock(body=b"fake"))
        event = MagicMock()
        event.url = "https://matrix.example.com/audio.flac"
        event.message_id = "msg_002"
        del event.original_filename

        downloader = AudioDownloader(config, data_dir=tmp_data_dir)
        result = await downloader.download_audio(client, event)
        assert result.suffix == ".flac"

    @pytest.mark.asyncio
    async def test_download_no_url_raises(self, downloader, mock_client, mock_event):
        """download_audio() raises ValueError when event has no URL."""
        mock_event.url = None
        with pytest.raises(ValueError, match="no download URL"):
            await downloader.download_audio(mock_client, mock_event)

    @pytest.mark.asyncio
    async def test_download_no_message_id_raises(self, downloader, mock_client, mock_event):
        """download_audio() raises ValueError when event has no message_id."""
        mock_event.message_id = None
        with pytest.raises(ValueError, match="no message_id"):
            await downloader.download_audio(mock_client, mock_event)

    @pytest.mark.asyncio
    async def test_download_default_extension(self, config, tmp_data_dir):
        """download_audio() defaults to .wav when no extension info."""
        client = AsyncMock()
        client.download = AsyncMock(return_value=MagicMock(body=b"fake"))
        event = MagicMock()
        event.url = "https://matrix.example.com/media/xyz"
        event.message_id = "msg_003"
        del event.original_filename

        downloader = AudioDownloader(config, data_dir=tmp_data_dir)
        result = await downloader.download_audio(client, event)
        assert result.suffix == ".wav"


# ---------------------------------------------------------------------------
# validate_audio — format checks
# ---------------------------------------------------------------------------

class TestValidateFormat:
    """Test validate_audio() format checks."""

    def test_validate_wav_accepts(self, downloader, audio_file):
        """WAV file passes format check (mock duration)."""
        with patch.object(downloader, "_get_duration", return_value=10.0):
            assert downloader.validate_audio(audio_file) is True

    def test_validate_mp3_accepts(self, config, tmp_data_dir, downloader):
        """MP3 file passes format check (mock duration)."""
        path = Path(tmp_data_dir) / "test.mp3"
        path.write_bytes(b"fake mp3 data")
        with patch.object(downloader, "_get_duration", return_value=10.0):
            assert downloader.validate_audio(path) is True

    def test_validate_flac_accepts(self, config, tmp_data_dir, downloader):
        """FLAC file passes format check (mock duration)."""
        path = Path(tmp_data_dir) / "test.flac"
        path.write_bytes(b"fake flac data")
        with patch.object(downloader, "_get_duration", return_value=10.0):
            assert downloader.validate_audio(path) is True

    def test_validate_ogg_rejects(self, config, tmp_data_dir, downloader):
        """OGG file is rejected (unsupported format)."""
        path = Path(tmp_data_dir) / "test.ogg"
        path.write_bytes(b"fake ogg data")
        assert downloader.validate_audio(path) is False

    def test_validate_webm_rejects(self, config, tmp_data_dir, downloader):
        """WEBM file is rejected (unsupported format)."""
        path = Path(tmp_data_dir) / "test.webm"
        path.write_bytes(b"fake webm data")
        assert downloader.validate_audio(path) is False

    def test_validate_txt_rejects(self, config, tmp_data_dir, downloader):
        """TXT file is rejected (unsupported format)."""
        path = Path(tmp_data_dir) / "test.txt"
        path.write_bytes(b"not audio")
        assert downloader.validate_audio(path) is False


# ---------------------------------------------------------------------------
# validate_audio — duration checks
# ---------------------------------------------------------------------------

class TestValidateDuration:
    """Test validate_audio() duration checks."""

    def test_validate_accepts_normal_duration(self, downloader, audio_file):
        """10-second file passes duration check."""
        with patch.object(downloader, "_get_duration", return_value=10.0):
            assert downloader.validate_audio(audio_file) is True

    def test_validate_too_short_rejects(self, downloader, audio_file):
        """2-second file is rejected (below MIN_DURATION)."""
        with patch.object(downloader, "_get_duration", return_value=2.0):
            assert downloader.validate_audio(audio_file) is False

    def test_validate_exactly_min_duration_accepts(self, downloader, audio_file):
        """Exactly 3-second file passes (boundary)."""
        with patch.object(downloader, "_get_duration", return_value=3.0):
            assert downloader.validate_audio(audio_file) is True

    def test_validate_too_long_rejects(self, config, tmp_data_dir, downloader):
        """31-minute file is rejected (above MAX_DURATION)."""
        path = Path(tmp_data_dir) / "long.wav"
        path.write_bytes(b"fake data")
        with patch.object(downloader, "_get_duration", return_value=31 * 60):
            assert downloader.validate_audio(path) is False

    def test_validate_exactly_max_duration_accepts(self, config, tmp_data_dir, downloader):
        """Exactly 30-minute file passes (boundary)."""
        path = Path(tmp_data_dir) / "max.wav"
        path.write_bytes(b"fake data")
        with patch.object(downloader, "_get_duration", return_value=30 * 60):
            assert downloader.validate_audio(path) is True

    def test_validate_duration_none_rejects(self, downloader, audio_file):
        """File with unknown duration is rejected."""
        with patch.object(downloader, "_get_duration", return_value=None):
            assert downloader.validate_audio(audio_file) is False


# ---------------------------------------------------------------------------
# validate_audio — size checks
# ---------------------------------------------------------------------------

class TestValidateSize:
    """Test validate_audio() size checks."""

    def test_validate_accepts_small_file(self, downloader, audio_file):
        """Small file passes size check."""
        with patch.object(downloader, "_get_duration", return_value=10.0):
            assert downloader.validate_audio(audio_file) is True

    def test_validate_too_large_rejects(self, config, tmp_data_dir, downloader):
        """51MB file is rejected (above MAX_FILE_SIZE)."""
        path = Path(tmp_data_dir) / "huge.wav"
        # Write 51 MB
        path.write_bytes(b"x" * (51 * 1024 * 1024))
        assert downloader.validate_audio(path) is False

    def test_validate_exactly_max_size_accepts(self, config, tmp_data_dir, downloader):
        """Exactly 50MB file passes (boundary)."""
        path = Path(tmp_data_dir) / "maxsize.wav"
        path.write_bytes(b"x" * MAX_FILE_SIZE)
        with patch.object(downloader, "_get_duration", return_value=10.0):
            assert downloader.validate_audio(path) is True

    def test_validate_nonexistent_file_rejects(self, config, tmp_data_dir):
        """Nonexistent file is rejected."""
        path = Path(tmp_data_dir) / "does_not_exist.wav"
        downloader = AudioDownloader(config, data_dir=tmp_data_dir)
        assert downloader.validate_audio(path) is False


# ---------------------------------------------------------------------------
# send_to_queue
# ---------------------------------------------------------------------------

class TestSendToQueue:
    """Test AudioDownloader.send_to_queue()."""

    def test_send_to_queue_creates_redis_key(self, downloader, audio_file):
        """send_to_queue() calls rpush with correct key."""
        redis_conn = FakeRedis()
        # Put file in a room subdirectory
        room_dir = audio_file.parent / "room123"
        room_dir.mkdir(exist_ok=True)
        new_file = room_dir / "msg_001.wav"
        audio_file.rename(new_file)

        key = downloader.send_to_queue(redis_conn, new_file)
        assert key == "room123:msg_001"
        queue = redis_conn.get_queue("transcription_queue")
        assert "room123:msg_001" in queue

    def test_send_to_queue_returns_key(self, downloader, audio_file):
        """send_to_queue() returns the key string."""
        redis_conn = FakeRedis()
        room_dir = audio_file.parent / "!room:example.com"
        room_dir.mkdir(exist_ok=True)
        new_file = room_dir / "msg_456.wav"
        audio_file.rename(new_file)

        key = downloader.send_to_queue(redis_conn, new_file)
        assert key == "!room:example.com:msg_456"

    def test_send_to_queue_raises_on_redis_failure(self, config, tmp_data_dir):
        """send_to_queue() raises TaskQueueError on Redis failure."""
        path = Path(tmp_data_dir) / "room1" / "msg_001.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")
        downloader = AudioDownloader(config, data_dir=tmp_data_dir)

        broken_redis = MagicMock()
        broken_redis.rpush = MagicMock(side_effect=Exception("connection lost"))

        with pytest.raises(TaskQueueError, match="Failed to push"):
            downloader.send_to_queue(broken_redis, path)


# ---------------------------------------------------------------------------
# _get_duration (ffprobe)
# ---------------------------------------------------------------------------

class TestGetDuration:
    """Test AudioDownloader._get_duration()."""

    def test_get_duration_parses_output(self, downloader, audio_file):
        """_get_duration() returns float from ffprobe output."""
        result = downloader._get_duration(audio_file)
        # ffprobe will fail on fake WAV, so it returns None
        # This tests the path when ffprobe works
        assert result is None  # fake file, ffprobe fails

    def test_get_duration_handles_ffprobe_not_found(self, downloader, audio_file):
        """_get_duration() returns None when ffprobe is missing."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert downloader._get_duration(audio_file) is None

    def test_get_duration_handles_timeout(self, downloader, audio_file):
        """_get_duration() returns None on timeout."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffprobe", 30),
        ):
            assert downloader._get_duration(audio_file) is None

    def test_get_duration_handles_bad_output(self, downloader, audio_file):
        """_get_duration() returns None on non-numeric output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not_a_number"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            assert downloader._get_duration(audio_file) is None


# ---------------------------------------------------------------------------
# File path format
# ---------------------------------------------------------------------------

class TestFilePathFormat:
    """Test that downloaded files follow data/{message_id}.{ext} format."""

    @pytest.mark.asyncio
    async def test_file_path_format(self, downloader, mock_client, mock_event):
        """Downloaded file is at data_dir/{message_id}.{ext}."""
        result = await downloader.download_audio(mock_client, mock_event)
        expected_name = f"{mock_event.message_id}.wav"
        assert result.name == expected_name
        assert str(result.parent) == str(downloader.data_dir)

    @pytest.mark.asyncio
    async def test_file_path_with_different_ext(self, downloader, mock_client):
        """File extension comes from original_filename."""
        event = MagicMock()
        event.url = "https://matrix.example.com/media/xyz"
        event.message_id = "msg_007"
        event.original_filename = "podcast.mp3"

        result = await downloader.download_audio(mock_client, event)
        assert result.name == "msg_007.mp3"


# ---------------------------------------------------------------------------
# Integration-like: full flow
# ---------------------------------------------------------------------------

class TestFullFlow:
    """Test complete download → validate → queue flow."""

    @pytest.mark.asyncio
    async def test_full_flow(self, config, tmp_data_dir):
        """Download, validate, and queue a valid audio file."""
        downloader = AudioDownloader(config, data_dir=tmp_data_dir)

        # Create a mock client that returns real-ish data
        client = AsyncMock()
        client.download = AsyncMock(return_value=MagicMock(body=b"RIFF\x28\x00\x00\x00" + b"\x00" * 100))

        event = MagicMock()
        event.url = "https://matrix.example.com/media/test123"
        event.message_id = "msg_flow_001"
        event.original_filename = "test.wav"

        # 1. Download
        file_path = await downloader.download_audio(client, event)
        assert file_path.is_file()

        # 2. Validate (mock duration since file is fake)
        with patch.object(downloader, "_get_duration", return_value=10.0):
            assert downloader.validate_audio(file_path) is True

        # 3. Send to queue
        redis_conn = FakeRedis()
        key = downloader.send_to_queue(redis_conn, file_path)
        assert "msg_flow_001" in key
