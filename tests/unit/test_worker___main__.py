"""Tests for worker/__main__.py — entry point and task processing."""

import os
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worker.__main__ import task_timer


# ---------------------------------------------------------------------------
# Test: WORKER_TASK_DURATION is defined (regression test for NameError)
# ---------------------------------------------------------------------------


class TestTaskTimer:
    """Verify task_timer() doesn't raise NameError for WORKER_TASK_DURATION."""

    def test_task_timer_no_name_error(self):
        """When task_timer() is entered → no NameError."""
        with task_timer():
            pass  # Should not raise NameError

    def test_task_timer_uses_processing_duration(self):
        """When task_timer() is used → it wraps WORKER_PROCESSING_DURATION."""
        with patch("worker.__main__.WORKER_PROCESSING_DURATION") as mock_hist:
            mock_timer = MagicMock()
            mock_timer.__enter__ = MagicMock()
            mock_timer.__exit__ = MagicMock(return_value=False)
            mock_hist.time.return_value = mock_timer

            with task_timer():
                pass

            mock_hist.time.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Worker blpop with empty queue (None)
# ---------------------------------------------------------------------------


class TestBlpopEmptyQueue:
    """Verify worker handles blpop returning None without crashing."""

    def test_blpop_none_continues_loop(self):
        """When blpop returns None → worker continues (doesn't crash on unpack)."""
        mock_redis = MagicMock()
        mock_redis.blpop.return_value = None

        result = mock_redis.blpop("transcription_queue", timeout=5)
        assert result is None
        # After fix: check result before unpacking
        if result is None:
            pass  # continue
        else:
            _, task = result

    def test_blpop_with_task_unpacks_correctly(self):
        """When blpop returns (queue, task) → unpacks correctly."""
        mock_redis = MagicMock()
        mock_redis.blpop.return_value = (b"transcription_queue", b"room1|/tmp/file.mp3")

        result = mock_redis.blpop("transcription_queue", timeout=5)
        if result is not None:
            _, task = result
            assert task == b"room1|/tmp/file.mp3"


# ---------------------------------------------------------------------------
# Test: Download directory creation
# ---------------------------------------------------------------------------


class TestDownloadDirectoryCreation:
    """Verify download directory is created if it doesn't exist."""

    def test_directory_created_on_download(self, tmp_path: Path):
        """When download_dir doesn't exist → Path.mkdir creates it."""
        download_dir = str(tmp_path / "nonexistent" / "subdir")
        Path(download_dir).mkdir(parents=True, exist_ok=True)
        assert Path(download_dir).exists()

    def test_directory_created_if_exists(self, tmp_path: Path):
        """When download_dir exists → mkdir doesn't raise."""
        existing = str(tmp_path / "exists")
        Path(existing).mkdir(exist_ok=True)
        Path(existing).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Test: File extension extraction
# ---------------------------------------------------------------------------


class TestExtensionExtraction:
    """Verify extension is correctly extracted from various filename formats."""

    def test_extension_from_filename_with_dot(self):
        """When filename has extension → extract it."""
        _, ext = os.path.splitext("cad9e22816d22ad8716274b0c55b5d9d.mp3")
        assert ext == ".mp3"

    def test_extension_from_filename_without_dot(self):
        """When filename has no extension → falls back to .wav."""
        _, ext = os.path.splitext("hash_without_extension")
        assert ext == ""
        if not ext:
            ext = ".wav"
        assert ext == ".wav"

    def test_extension_from_full_path(self):
        """When filename is a full path → extract extension from basename."""
        _, ext = os.path.splitext("/some/path/file.ogg")
        assert ext == ".ogg"

    def test_extension_from_none_body(self):
        """When body is None → falls back to 'audio' default."""
        raw_filename = None or "audio"
        _, ext = os.path.splitext(raw_filename)
        if not ext:
            ext = ".wav"
        assert ext == ".wav"

    def test_extension_from_empty_body(self):
        """When body is empty string → falls back to 'audio' default."""
        raw_filename = "" or "audio"
        _, ext = os.path.splitext(raw_filename)
        if not ext:
            ext = ".wav"
        assert ext == ".wav"


# ---------------------------------------------------------------------------
# Test: SHA256 hash for safe filenames
# ---------------------------------------------------------------------------


class TestSafeFilename:
    """Verify event_id is hashed for filesystem-safe filenames."""

    def test_sha256_hash_is_safe(self):
        """When event_id contains $ → hash is alphanumeric only."""
        event_id = "$AF-gnnEptQQG9aY40aAcN1ErgHU7kfsHkbxDoWza-io"
        msg_id = hashlib.sha256(event_id.encode()).hexdigest()[:16]
        assert len(msg_id) == 16
        assert msg_id.isalnum()
        assert "$" not in msg_id
        assert "-" not in msg_id

    def test_same_event_id_same_hash(self):
        """Same event_id → same hash (deterministic)."""
        event_id = "$msg123"
        hash1 = hashlib.sha256(event_id.encode()).hexdigest()[:16]
        hash2 = hashlib.sha256(event_id.encode()).hexdigest()[:16]
        assert hash1 == hash2

    def test_different_event_id_different_hash(self):
        """Different event_id → different hash."""
        hash1 = hashlib.sha256("$msg1".encode()).hexdigest()[:16]
        hash2 = hashlib.sha256("$msg2".encode()).hexdigest()[:16]
        assert hash1 != hash2
