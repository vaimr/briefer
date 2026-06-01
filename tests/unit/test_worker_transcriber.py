"""Unit tests for worker/transcriber.py — Whisper transcription via faster_whisper."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestTranscriberInit:
    """Tests for Transcriber initialization."""

    def test_initializes_with_model(self):
        """Given: default model_name and device
        When: Transcriber is instantiated
        Then: model attribute is a WhisperModel instance"""
        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model_cls.return_value = MagicMock()
            from worker.transcriber import Transcriber
            t = Transcriber()
            assert t.model is not None
            mock_model_cls.assert_called_once_with(
                "large-v3", device="cpu", compute_type="int8"
            )

    def test_initializes_with_custom_model(self):
        """Given: custom model_name and device
        When: Transcriber is instantiated
        Then: WhisperModel called with provided args"""
        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model_cls.return_value = MagicMock()
            from worker.transcriber import Transcriber
            t = Transcriber(model_name="base", device="cuda")
            assert t.model_name == "base"
            assert t.device == "cuda"
            mock_model_cls.assert_called_once_with(
                "base", device="cuda", compute_type="int8"
            )

    def test_model_not_loaded_raises_value_error(self):
        """Given: model is None
        When: Transcriber is instantiated
        Then: ValueError is raised"""
        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model_cls.side_effect = Exception("Model load failed")
            from worker.transcriber import Transcriber
            with pytest.raises(ValueError, match="Failed to load Whisper model"):
                Transcriber()


class TestTranscribe:
    """Tests for Transcriber.transcribe method."""

    def _make_wav(self, tmp_path, name="test.wav", duration=5.0):
        """Helper to create a fake WAV file with proper duration info."""
        wav = tmp_path / name
        # Write a minimal valid WAV header
        import struct
        num_samples = int(duration * 16000)
        data = b"\x00" * (num_samples * 2)  # 16-bit mono
        wav.write_bytes(
            b"RIFF"
            + struct.pack("<I", 36 + len(data))
            + b"WAVE"
            + b"fmt "
            + struct.pack("<I", 16)
            + struct.pack("<H", 1)  # PCM
            + struct.pack("<H", 1)  # mono
            + struct.pack("<I", 16000)  # sample rate
            + struct.pack("<I", 16000 * 2)  # byte rate
            + struct.pack("<H", 2)  # block align
            + struct.pack("<H", 16)  # bits per sample
            + b"data"
            + struct.pack("<I", len(data))
            + data
        )
        return wav

    def test_transcribe_returns_text(self, tmp_path):
        """Given: a valid 16kHz mono WAV file
        When: transcribe() is called
        Then: returns dict with 'text' key containing non-empty string"""
        wav = self._make_wav(tmp_path, duration=3.0)
        mock_segment = MagicMock()
        mock_segment.text = "Привет мир"
        mock_segment.start = 0.0
        mock_segment.end = 3.0
        mock_info = MagicMock()
        mock_info.language = "ru"
        mock_info.duration = 3.0

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([mock_segment], mock_info)
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            result = t.transcribe(wav)
            assert "text" in result
            assert isinstance(result["text"], str)
            assert len(result["text"]) > 0

    def test_transcribe_returns_segments(self, tmp_path):
        """Given: a valid WAV file with multiple segments
        When: transcribe() is called
        Then: returns dict with 'segments' key containing list of dicts"""
        wav = self._make_wav(tmp_path, duration=3.0)
        seg1 = MagicMock()
        seg1.text = "Первая"
        seg1.start = 0.0
        seg1.end = 1.5
        seg2 = MagicMock()
        seg2.text = "Вторая"
        seg2.start = 1.5
        seg2.end = 3.0
        mock_info = MagicMock()
        mock_info.language = "ru"
        mock_info.duration = 3.0

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([seg1, seg2], mock_info)
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            result = t.transcribe(wav)
            assert "segments" in result
            assert isinstance(result["segments"], list)
            assert len(result["segments"]) == 2
            assert result["segments"][0]["text"] == "Первая"
            assert result["segments"][0]["start"] == 0.0
            assert result["segments"][0]["end"] == 1.5

    def test_transcribe_returns_duration(self, tmp_path):
        """Given: a valid WAV file
        When: transcribe() is called
        Then: returns dict with 'duration' key matching file duration"""
        wav = self._make_wav(tmp_path, duration=7.5)
        mock_segment = MagicMock()
        mock_segment.text = "Текст"
        mock_segment.start = 0.0
        mock_segment.end = 7.5
        mock_info = MagicMock()
        mock_info.language = "ru"
        mock_info.duration = 7.5

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([mock_segment], mock_info)
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            result = t.transcribe(wav)
            assert "duration" in result
            assert isinstance(result["duration"], float)
            assert result["duration"] == pytest.approx(7.5, abs=0.01)

    def test_transcribe_returns_language(self, tmp_path):
        """Given: a valid WAV file
        When: transcribe() is called
        Then: returns dict with 'language' key"""
        wav = self._make_wav(tmp_path, duration=3.0)
        mock_segment = MagicMock()
        mock_segment.text = "Тест"
        mock_segment.start = 0.0
        mock_segment.end = 3.0
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 3.0

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([mock_segment], mock_info)
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            result = t.transcribe(wav)
            assert "language" in result
            assert result["language"] == "en"

    def test_transcribe_file_not_found_raises(self, tmp_path):
        """Given: a file path that does not exist
        When: transcribe() is called
        Then: FileNotFoundError is raised"""
        missing = tmp_path / "does_not_exist.wav"
        with patch("worker.transcriber.WhisperModel"):
            from worker.transcriber import Transcriber
            t = Transcriber()
            with pytest.raises(FileNotFoundError, match="File not found"):
                t.transcribe(missing)

    def test_transcribe_empty_file_raises(self, tmp_path):
        """Given: a WAV file with 0 duration
        When: transcribe() is called
        Then: ValueError is raised"""
        wav = tmp_path / "empty.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 44 + b"WAVE" + b"fmt " + b"\x00" * 16 + b"data" + b"\x00" * 4)

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            with patch.object(t, "_get_duration", return_value=0.0):
                with pytest.raises(ValueError, match="Empty"):
                    t.transcribe(wav)

    def test_transcribe_too_long_file_raises(self, tmp_path):
        """Given: a WAV file > 30 minutes
        When: transcribe() is called
        Then: ValueError is raised"""
        wav = self._make_wav(tmp_path, duration=1801)  # ~30 min
        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            with pytest.raises(ValueError, match="too long"):
                t.transcribe(wav)

    def test_transcribe_tiny_audio_returns_empty_text(self, tmp_path):
        """Given: a 1-second WAV file with silence
        When: transcribe() is called
        Then: returns dict with text = "" (no speech detected)"""
        wav = self._make_wav(tmp_path, duration=1.0)
        mock_info = MagicMock()
        mock_info.language = "ru"
        mock_info.duration = 1.0

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([], mock_info)  # no segments
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            result = t.transcribe(wav)
            assert "text" in result
            assert result["text"] == ""

    def test_transcribe_calls_whisper_with_correct_params(self, tmp_path):
        """Given: a valid WAV file
        When: transcribe() is called
        Then: model.transcribe called with beam_size=5, language="ru"
        And: wav_path is passed as string"""
        wav = self._make_wav(tmp_path, duration=3.0)
        mock_segment = MagicMock()
        mock_segment.text = "Тест"
        mock_segment.start = 0.0
        mock_segment.end = 3.0
        mock_info = MagicMock()
        mock_info.language = "ru"
        mock_info.duration = 3.0

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([mock_segment], mock_info)
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            t.transcribe(wav)
            mock_model.transcribe.assert_called_once()
            call_args = mock_model.transcribe.call_args
            assert call_args[0][0] == str(wav)
            assert call_args[1]["language"] == "ru"
            assert call_args[1]["beam_size"] == 5

    def test_transcribe_strips_whitespace(self, tmp_path):
        """Given: a WAV file with text that has leading/trailing whitespace
        When: transcribe() is called
        Then: returned text is stripped"""
        wav = self._make_wav(tmp_path, duration=3.0)
        mock_segment = MagicMock()
        mock_segment.text = "  Привет  "
        mock_segment.start = 0.0
        mock_segment.end = 3.0
        mock_info = MagicMock()
        mock_info.language = "ru"
        mock_info.duration = 3.0

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([mock_segment], mock_info)
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            result = t.transcribe(wav)
            assert result["text"] == "Привет"

    def test_transcribe_multiple_segments_joined(self, tmp_path):
        """Given: multiple segments
        When: transcribe() is called
        Then: text is all segment texts joined together"""
        wav = self._make_wav(tmp_path, duration=5.0)
        seg1 = MagicMock()
        seg1.text = "Первая часть"
        seg1.start = 0.0
        seg1.end = 2.5
        seg2 = MagicMock()
        seg2.text = "Вторая часть"
        seg2.start = 2.5
        seg2.end = 5.0
        mock_info = MagicMock()
        mock_info.language = "ru"
        mock_info.duration = 5.0

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([seg1, seg2], mock_info)
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            result = t.transcribe(wav)
            assert result["text"] == "Первая частьВторая часть"

    def test_transcribe_segment_structure(self, tmp_path):
        """Given: a WAV file with segments
        When: transcribe() is called
        Then: each segment dict has text, start, end keys"""
        wav = self._make_wav(tmp_path, duration=3.0)
        seg = MagicMock()
        seg.text = "Текст"
        seg.start = 1.0
        seg.end = 2.0
        mock_info = MagicMock()
        mock_info.language = "ru"
        mock_info.duration = 3.0

        with patch("worker.transcriber.WhisperModel") as mock_model_cls:
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([seg], mock_info)
            mock_model_cls.return_value = mock_model
            from worker.transcriber import Transcriber
            t = Transcriber()
            result = t.transcribe(wav)
            seg_dict = result["segments"][0]
            assert "text" in seg_dict
            assert "start" in seg_dict
            assert "end" in seg_dict
            assert seg_dict["text"] == "Текст"
            assert seg_dict["start"] == 1.0
            assert seg_dict["end"] == 2.0
