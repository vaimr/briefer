"""Tests for worker/pipeline.py: parse_task and process_transcription_task."""

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── parse_task ────────────────────────────────────────────────────────────────


class TestParseTask:
    """parse_task(task_str) -> (room_id, audio_path)"""

    def test_parse_task_valid(self):
        """Given: "room1|/data/input/test.mp3"
        When: parsed
        Then: returns ("room1", "/data/input/test.mp3")"""
        from worker.pipeline import parse_task

        room_id, audio_path = parse_task("room1|/data/input/test.mp3")

        assert room_id == "room1"
        assert audio_path == "/data/input/test.mp3"

    def test_parse_task_with_spaces_in_path(self):
        """Given: room_id and path with spaces
        When: parsed
        Then: both parts preserved exactly"""
        from worker.pipeline import parse_task

        room_id, audio_path = parse_task("room2|/data/my folder/file.mp3")

        assert room_id == "room2"
        assert audio_path == "/data/my folder/file.mp3"

    def test_parse_task_multiple_pipes_returns_first_and_rest(self):
        """Given: "room|/path/with|pipe"
        When: parsed
        Then: splits on first | only — audio_path contains remaining pipes"""
        from worker.pipeline import parse_task

        room_id, audio_path = parse_task("room3|/data/path|with|pipes")

        assert room_id == "room3"
        assert audio_path == "/data/path|with|pipes"

    def test_parse_task_missing_pipe_raises(self):
        """Given: string without |
        When: parsed
        Then: raises ValueError"""
        from worker.pipeline import parse_task

        with pytest.raises(ValueError, match="Invalid task format"):
            parse_task("no-pipe-here")

    def test_parse_task_empty_room_raises(self):
        """Given: "|/path"
        When: parsed
        Then: raises ValueError for empty room_id"""
        from worker.pipeline import parse_task

        with pytest.raises(ValueError, match="Task parts cannot be empty"):
            parse_task("|/data/file.mp3")

    def test_parse_task_empty_path_raises(self):
        """Given: "room|"
        When: parsed
        Then: raises ValueError for empty audio_path"""
        from worker.pipeline import parse_task

        with pytest.raises(ValueError, match="Task parts cannot be empty"):
            parse_task("room|")

    def test_parse_task_empty_string_raises(self):
        """Given: empty string
        When: parsed
        Then: raises ValueError"""
        from worker.pipeline import parse_task

        with pytest.raises(ValueError, match="Invalid task format"):
            parse_task("")

    def test_parse_task_only_pipe_raises(self):
        """Given: "|"
        When: parsed
        Then: raises ValueError"""
        from worker.pipeline import parse_task

        with pytest.raises(ValueError, match="Task parts cannot be empty"):
            parse_task("|")


# ── process_transcription_task ────────────────────────────────────────────────


class TestProcessTranscriptionTask:
    """process_transcription_task(task_str, config) -> dict"""

    def _make_config(self, data_dir: str = "/tmp/briefer_test"):
        """Create a minimal mock config."""
        config = MagicMock()
        config.data_dir = data_dir
        config.whisper_model = "large-v3"
        return config

    def _create_temp_audio_file(self, tmp_path: Path, name: str = "test.mp3") -> str:
        """Create a small dummy file to simulate audio."""
        path = tmp_path / name
        path.write_bytes(b"dummy audio content")
        return str(path)

    def test_process_task_nonexistent_file_raises(self):
        """Given: task with nonexistent audio path
        When: processed
        Then: raises FileNotFoundError"""
        from worker.pipeline import process_transcription_task

        config = self._make_config()

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            process_transcription_task(
                "room1|/nonexistent/path/audio.mp3",
                config,
            )

    def test_process_task_returns_dict_with_keys(self):
        """Given: valid task with existing audio file
        When: processed with mocked audio + transcriber
        Then: returns dict with all required keys"""
        from worker.pipeline import process_transcription_task

        with tempfile.TemporaryDirectory() as tmp_path:
            audio_path = self._create_temp_audio_file(Path(tmp_path), "test.mp3")
            config = self._make_config(tmp_path)

            mock_wav_path = os.path.join(tmp_path, "test.wav")
            # Create the mock WAV file so convert_to_wav doesn't fail
            Path(mock_wav_path).write_bytes(b"WAV dummy")

            with (
                patch("worker.pipeline.convert_to_wav") as mock_convert,
                patch("worker.pipeline.transcribe_wav") as mock_transcribe,
            ):
                mock_convert.return_value = (mock_wav_path, 10.5)
                mock_transcribe.return_value = (
                    "Привет мир",
                    [{"start": 0.0, "end": 1.0, "text": "Привет"}],
                )

                result = process_transcription_task(
                    "room1|" + audio_path,
                    config,
                )

            assert isinstance(result, dict)
            assert result["room_id"] == "room1"
            assert result["audio_path"] == audio_path
            assert result["transcript"] == "Привет мир"
            assert result["wav_path"] == mock_wav_path
            assert result["duration"] == 10.5
            assert isinstance(result["segments"], list)

    def test_process_task_logs_start_and_complete(self, caplog):
        """Given: valid task
        When: processed
        Then: logs START_TRANSCRIPTION and TRANSCRIPTION_COMPLETE"""
        from worker.pipeline import process_transcription_task

        with tempfile.TemporaryDirectory() as tmp_path:
            audio_path = self._create_temp_audio_file(Path(tmp_path), "test.mp3")
            config = self._make_config(tmp_path)

            mock_wav_path = os.path.join(tmp_path, "test.wav")
            Path(mock_wav_path).write_bytes(b"WAV dummy")

            with (
                patch("worker.pipeline.convert_to_wav") as mock_convert,
                patch("worker.pipeline.transcribe_wav") as mock_transcribe,
            ):
                mock_convert.return_value = (mock_wav_path, 5.0)
                mock_transcribe.return_value = ("Text", [])

                with caplog.at_level(logging.INFO):
                    process_transcription_task(
                        "room2|" + audio_path,
                        config,
                    )

            assert any("START_TRANSCRIPTION" in r.message for r in caplog.records)
            assert any("TRANSCRIPTION_COMPLETE" in r.message for r in caplog.records)

    def test_process_task_calls_convert_to_wav_with_correct_args(self):
        """Given: valid task
        When: processed
        Then: convert_to_wav(audio_path, config.data_dir) called once"""
        from worker.pipeline import process_transcription_task

        with tempfile.TemporaryDirectory() as tmp_path:
            audio_path = self._create_temp_audio_file(Path(tmp_path), "test.mp3")
            config = self._make_config(tmp_path)

            mock_wav_path = os.path.join(tmp_path, "test.wav")
            Path(mock_wav_path).write_bytes(b"WAV dummy")

            with (
                patch("worker.pipeline.convert_to_wav") as mock_convert,
                patch("worker.pipeline.transcribe_wav") as mock_transcribe,
            ):
                mock_convert.return_value = (mock_wav_path, 5.0)
                mock_transcribe.return_value = ("Text", [])

                process_transcription_task("room1|" + audio_path, config)

            mock_convert.assert_called_once_with(audio_path, tmp_path)

    def test_process_task_calls_transcribe_wav_with_wav_path(self):
        """Given: valid task
        When: processed
        Then: transcribe_wav(wav_path, config.whisper_model) called once"""
        from worker.pipeline import process_transcription_task

        with tempfile.TemporaryDirectory() as tmp_path:
            audio_path = self._create_temp_audio_file(Path(tmp_path), "test.mp3")
            config = self._make_config(tmp_path)

            mock_wav_path = os.path.join(tmp_path, "test.wav")
            Path(mock_wav_path).write_bytes(b"WAV dummy")

            with (
                patch("worker.pipeline.convert_to_wav") as mock_convert,
                patch("worker.pipeline.transcribe_wav") as mock_transcribe,
            ):
                mock_convert.return_value = (mock_wav_path, 5.0)
                mock_transcribe.return_value = ("Text", [])

                process_transcription_task("room1|" + audio_path, config)

            mock_transcribe.assert_called_once_with(mock_wav_path, "large-v3")

    def test_process_task_empty_transcript_warns_but_continues(self, caplog):
        """Given: transcription returns empty text
        When: processed
        Then: logs WARNING but does NOT raise"""
        from worker.pipeline import process_transcription_task

        with tempfile.TemporaryDirectory() as tmp_path:
            audio_path = self._create_temp_audio_file(Path(tmp_path), "test.mp3")
            config = self._make_config(tmp_path)

            mock_wav_path = os.path.join(tmp_path, "test.wav")
            Path(mock_wav_path).write_bytes(b"WAV dummy")

            with (
                patch("worker.pipeline.convert_to_wav") as mock_convert,
                patch("worker.pipeline.transcribe_wav") as mock_transcribe,
            ):
                mock_convert.return_value = (mock_wav_path, 5.0)
                mock_transcribe.return_value = ("", [])

                with caplog.at_level(logging.INFO):
                    result = process_transcription_task(
                        "room1|" + audio_path,
                        config,
                    )

            assert result["transcript"] == ""
            assert any(
                r.levelname == "WARNING" and "Empty transcript" in r.message
                for r in caplog.records
            )

    def test_process_task_parse_error_propagates(self):
        """Given: invalid task string
        When: processed
        Then: ValueError from parse_task propagates"""
        from worker.pipeline import process_transcription_task

        config = self._make_config()

        with pytest.raises(ValueError, match="Invalid task format"):
            process_transcription_task("invalid-no-pipe", config)

    def test_process_task_returns_correct_segment_structure(self):
        """Given: transcription with multiple segments
        When: processed
        Then: segments list preserved in result"""
        from worker.pipeline import process_transcription_task

        with tempfile.TemporaryDirectory() as tmp_path:
            audio_path = self._create_temp_audio_file(Path(tmp_path), "test.mp3")
            config = self._make_config(tmp_path)

            mock_wav_path = os.path.join(tmp_path, "test.wav")
            Path(mock_wav_path).write_bytes(b"WAV dummy")

            segments = [
                {"start": 0.0, "end": 1.5, "text": "First"},
                {"start": 1.5, "end": 3.0, "text": "Second"},
            ]

            with (
                patch("worker.pipeline.convert_to_wav") as mock_convert,
                patch("worker.pipeline.transcribe_wav") as mock_transcribe,
            ):
                mock_convert.return_value = (mock_wav_path, 3.0)
                mock_transcribe.return_value = ("First Second", segments)

                result = process_transcription_task(
                    "room1|" + audio_path,
                    config,
                )

            assert len(result["segments"]) == 2
            assert result["segments"][0]["text"] == "First"
            assert result["segments"][1]["text"] == "Second"
