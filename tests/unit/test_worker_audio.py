"""Unit tests for worker/audio.py — audio conversion via ffmpeg."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGetDuration:
    """Tests for _get_duration helper."""

    def test_returns_float(self, tmp_path):
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 100)
        with patch("worker.audio.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="3.1415\n")
            from worker.audio import _get_duration
            result = _get_duration(str(wav))
            assert isinstance(result, float)
            assert result == pytest.approx(3.1415, abs=0.001)

    def test_calls_ffprobe_correct_args(self, tmp_path):
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 100)
        with patch("worker.audio.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="5.0\n")
            from worker.audio import _get_duration
            _get_duration(str(wav))
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "ffprobe" in args
            assert "-v" in args
            assert "error" in args
            assert str(wav) in args

    def test_raises_on_ffprobe_failure(self, tmp_path):
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 100)
        with patch("worker.audio.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe", stderr="error")
            from worker.audio import _get_duration
            with pytest.raises(subprocess.CalledProcessError):
                _get_duration(str(wav))


class TestConvertToWav:
    """Tests for convert_to_wav function."""

    def test_creates_wav_file(self, tmp_path):
        """Given: a valid MP3 file
        When: convert_to_wav is called
        Then: WAV file is created in output_dir"""
        mp3 = tmp_path / "input.mp3"
        mp3.write_bytes(b"fake mp3 data")
        output_dir = tmp_path / "output"

        def create_wav(*args, **kwargs):
            wav = output_dir / "input.wav"
            wav.write_bytes(b"RIFF" + b"\x00" * 100)
            return MagicMock(returncode=0, stderr="")

        with patch("worker.audio.subprocess.run", side_effect=create_wav):
            with patch("worker.audio._get_duration", return_value=5.0):
                from worker.audio import convert_to_wav
                wav_path, duration = convert_to_wav(str(mp3), str(output_dir))

                assert wav_path == str(output_dir / "input.wav")
                assert duration == 5.0
                assert (output_dir / "input.wav").exists()

    def test_creates_output_dir_if_missing(self, tmp_path):
        """Given: output_dir does not exist
        When: convert_to_wav is called
        Then: output_dir is created"""
        mp3 = tmp_path / "input.mp3"
        mp3.write_bytes(b"fake mp3 data")
        output_dir = tmp_path / "nonexistent" / "output"

        def create_wav(*args, **kwargs):
            wav = output_dir / "input.wav"
            wav.write_bytes(b"RIFF" + b"\x00" * 100)
            return MagicMock(returncode=0, stderr="")

        with patch("worker.audio.subprocess.run", side_effect=create_wav):
            with patch("worker.audio._get_duration", return_value=5.0):
                from worker.audio import convert_to_wav
                convert_to_wav(str(mp3), str(output_dir))

                assert output_dir.exists()

    def test_nonexistent_file_raises(self, tmp_path):
        """Given: audio file does not exist
        When: convert_to_wav is called
        Then: FileNotFoundError is raised"""
        missing = tmp_path / "missing.mp3"

        with patch("worker.audio.subprocess.run"):
            from worker.audio import convert_to_wav
            with pytest.raises(FileNotFoundError, match="Audio file not found"):
                convert_to_wav(str(missing), str(tmp_path))

    def test_ffmpeg_error_raises_runtime_error(self, tmp_path):
        """Given: ffmpeg fails (exit code != 0)
        When: convert_to_wav is called
        Then: RuntimeError is raised with stderr message"""
        mp3 = tmp_path / "input.mp3"
        mp3.write_bytes(b"fake mp3 data")

        err_msg = "Unsupported format"
        with patch("worker.audio.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "ffmpeg", stderr=err_msg
            )
            from worker.audio import convert_to_wav
            with pytest.raises(RuntimeError, match="ffmpeg conversion failed"):
                convert_to_wav(str(mp3), str(tmp_path))

    def test_empty_wav_raises(self, tmp_path):
        """Given: ffmpeg succeeds but WAV is empty
        When: convert_to_wav is called
        Then: FileNotFoundError is raised"""
        mp3 = tmp_path / "input.mp3"
        mp3.write_bytes(b"fake mp3 data")

        # Create WAV file but it's empty
        wav = tmp_path / "input.wav"
        wav.write_bytes(b"")

        with patch("worker.audio.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            with patch("worker.audio._get_duration", return_value=0.0):
                from worker.audio import convert_to_wav
                with pytest.raises(FileNotFoundError, match="WAV file not created or empty"):
                    convert_to_wav(str(mp3), str(tmp_path))

    def test_calls_ffmpeg_with_correct_args(self, tmp_path):
        """Given: valid input
        When: convert_to_wav is called
        Then: ffmpeg called with -ar 16000 -ac 1 -y"""
        mp3 = tmp_path / "input.mp3"
        mp3.write_bytes(b"fake mp3 data")

        def create_wav(*args, **kwargs):
            wav = tmp_path / "input.wav"
            wav.write_bytes(b"RIFF" + b"\x00" * 100)
            return MagicMock(returncode=0, stderr="")

        with patch("worker.audio.subprocess.run", side_effect=create_wav) as mock_run:
            with patch("worker.audio._get_duration", return_value=5.0):
                from worker.audio import convert_to_wav
                convert_to_wav(str(mp3), str(tmp_path))

                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                assert "ffmpeg" in args
                assert "-i" in args
                assert str(mp3) in args
                assert "-ar" in args
                assert "16000" in args
                assert "-ac" in args
                assert "1" in args
                assert "-y" in args

    def test_returns_tuple_of_str_and_float(self, tmp_path):
        """Given: valid input
        When: convert_to_wav is called
        Then: returns (str, float)"""
        mp3 = tmp_path / "input.mp3"
        mp3.write_bytes(b"fake mp3 data")

        def create_wav(*args, **kwargs):
            wav = tmp_path / "input.wav"
            wav.write_bytes(b"RIFF" + b"\x00" * 100)
            return MagicMock(returncode=0, stderr="")

        with patch("worker.audio.subprocess.run", side_effect=create_wav):
            with patch("worker.audio._get_duration", return_value=10.5):
                from worker.audio import convert_to_wav
                result = convert_to_wav(str(mp3), str(tmp_path))

                assert isinstance(result, tuple)
                assert len(result) == 2
                assert isinstance(result[0], str)
                assert isinstance(result[1], float)

    def test_logs_conversion(self, tmp_path):
        """Given: valid input
        When: convert_to_wav is called
        Then: logger.info is called with conversion details"""
        mp3 = tmp_path / "input.mp3"
        mp3.write_bytes(b"fake mp3 data")

        def create_wav(*args, **kwargs):
            wav = tmp_path / "input.wav"
            wav.write_bytes(b"RIFF" + b"\x00" * 100)
            return MagicMock(returncode=0, stderr="")

        with patch("worker.audio.subprocess.run", side_effect=create_wav):
            with patch("worker.audio._get_duration", return_value=5.0):
                from worker.audio import convert_to_wav
                with patch("worker.audio.logger") as mock_logger:
                    convert_to_wav(str(mp3), str(tmp_path))
                    mock_logger.info.assert_called_once()
                    call_args = mock_logger.info.call_args[0]
                    assert "input.mp3" in str(call_args)
                    assert "input.wav" in str(call_args)
