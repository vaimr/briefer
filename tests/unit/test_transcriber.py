"""Unit tests for worker/transcriber.py."""

import struct
import wave
from pathlib import Path

import pytest

from worker.transcriber import Transcriber


AUDIO_DIR = Path(__file__).parent.parent / "audio"


def _make_silence_wav(path: Path, seconds: float, sample_rate: int = 16000) -> Path:
    """Create a WAV file with silence (zero samples).

    Args:
        path: Output file path.
        seconds: Duration in seconds.
        sample_rate: Sample rate in Hz.

    Returns:
        Path to the created file.
    """
    num_frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_frames)
    return path


@pytest.fixture()
def silence_1s(tmp_path: Path) -> Path:
    """1 second of silence at 16kHz mono 16-bit."""
    return _make_silence_wav(tmp_path / "silence_1s.wav", 1.0)


@pytest.fixture()
def empty_audio(tmp_path: Path) -> Path:
    """0 second WAV file (0 frames)."""
    return _make_silence_wav(tmp_path / "empty.wav", 0.0)


@pytest.fixture()
def too_long_audio(tmp_path: Path) -> Path:
    """31-minute WAV file (31 * 60 + 1 seconds)."""
    return _make_silence_wav(tmp_path / "too_long.wav", 31 * 60 + 1)


class TestTranscriberInitialization:
    """Tests for Transcriber.__init__."""

    def test_transcriber_initializes_with_model(self):
        """Given default args, Transcriber loads WhisperModel successfully.

        When: Transcriber(model_name="large-v3", device="cpu") is created
        Then: self.model is a WhisperModel instance (not None)
              self.model_name == "large-v3"
              self.device == "cpu"
        """
        t = Transcriber()
        assert t.model is not None
        assert t.model_name == "large-v3"
        assert t.device == "cpu"

    def test_transcriber_initializes_with_custom_model(self):
        """Given custom model_name, Transcriber uses that model.

        When: Transcriber(model_name="base") is created
        Then: self.model_name == "base"
              self.model is not None
        """
        t = Transcriber(model_name="base")
        assert t.model_name == "base"
        assert t.model is not None


class TestTranscribeReturnsData:
    """Tests for Transcribe output structure (uses real audio files)."""

    def test_transcribe_returns_text(self):
        """Given a real WAV file, transcribe returns non-empty text.

        When: transcribe() is called with tests/audio/short_meeting.wav
        Then: result["text"] is a non-empty string
        """
        audio_path = AUDIO_DIR / "short_meeting.wav"
        if not audio_path.exists():
            pytest.skip("short_meeting.wav not available")

        t = Transcriber()
        result = t.transcribe(audio_path)
        assert isinstance(result["text"], str)
        assert len(result["text"]) > 0

    def test_transcribe_returns_segments(self):
        """Given a real WAV file, transcribe returns segments list.

        When: transcribe() is called with tests/audio/short_meeting.wav
        Then: result["segments"] is a list
        """
        audio_path = AUDIO_DIR / "short_meeting.wav"
        if not audio_path.exists():
            pytest.skip("short_meeting.wav not available")

        t = Transcriber()
        result = t.transcribe(audio_path)
        assert isinstance(result["segments"], list)

    def test_transcribe_returns_duration(self):
        """Given a real WAV file, duration matches file duration.

        When: transcribe() is called with tests/audio/short_meeting.wav
        Then: result["duration"] matches the actual WAV file duration
        """
        audio_path = AUDIO_DIR / "short_meeting.wav"
        if not audio_path.exists():
            pytest.skip("short_meeting.wav not available")

        t = Transcriber()
        result = t.transcribe(audio_path)

        # Verify duration matches the actual WAV file
        with wave.open(str(audio_path), "rb") as wf:
            expected_duration = wf.getnframes() / wf.getframerate()
        assert abs(result["duration"] - expected_duration) < 0.1

    def test_transcribe_returns_language(self):
        """Given a real WAV file, transcribe returns detected language.

        When: transcribe() is called with tests/audio/short_meeting.wav
        Then: result["language"] is a string
        """
        audio_path = AUDIO_DIR / "short_meeting.wav"
        if not audio_path.exists():
            pytest.skip("short_meeting.wav not available")

        t = Transcriber()
        result = t.transcribe(audio_path)
        assert isinstance(result["language"], str)


class TestTranscribeErrorCases:
    """Tests for Transcribe error handling."""

    def test_transcribe_file_not_found_raises(self):
        """Given a non-existent file, transcribe raises FileNotFoundError.

        When: transcribe() is called with a Path that does not exist
        Then: FileNotFoundError is raised with message containing the path
        """
        t = Transcriber()
        with pytest.raises(FileNotFoundError, match="File not found"):
            t.transcribe(Path("/nonexistent/path/audio.wav"))

    def test_transcribe_empty_file_raises(self, empty_audio: Path):
        """Given a 0-second WAV file, transcribe raises ValueError.

        When: transcribe() is called with a WAV file with 0 duration
        Then: ValueError is raised with message containing "Empty"
        """
        assert empty_audio.exists()
        t = Transcriber()
        with pytest.raises(ValueError, match="Empty"):
            t.transcribe(empty_audio)

    def test_transcribe_too_long_file_raises(self, too_long_audio: Path):
        """Given a >30min WAV file, transcribe raises ValueError.

        When: transcribe() is called with a WAV file > 1800 seconds
        Then: ValueError is raised with message containing "too long"
        """
        assert too_long_audio.exists()
        t = Transcriber()
        with pytest.raises(ValueError, match="too long"):
            t.transcribe(too_long_audio)


class TestTranscribeEdgeCases:
    """Tests for Transcribe edge cases."""

    def test_transcribe_tiny_audio_returns_text(self, silence_1s: Path):
        """Given a 1-second silence WAV, transcribe returns a text result.

        When: transcribe() is called with a WAV file containing only silence
        Then: result["text"] is a string (Whisper may hallucinate on silence)
        """
        t = Transcriber()
        result = t.transcribe(silence_1s)
        assert isinstance(result["text"], str)
        assert len(result["text"]) > 0

    def test_transcribe_tiny_audio_returns_duration(self, silence_1s: Path):
        """Given a 1-second silence WAV, duration equals 1.0.

        When: transcribe() is called with a 1-second WAV file
        Then: result["duration"] == 1.0
        """
        t = Transcriber()
        result = t.transcribe(silence_1s)
        assert result["duration"] == pytest.approx(1.0, abs=0.01)

    def test_transcribe_segment_structure(self, silence_1s: Path):
        """Given a WAV file, each segment has text, start, end keys.

        When: transcribe() is called
        Then: each segment dict contains "text", "start", "end" keys
              "start" and "end" are numeric
        """
        t = Transcriber()
        result = t.transcribe(silence_1s)
        for seg in result["segments"]:
            assert "text" in seg
            assert "start" in seg
            assert "end" in seg
            assert isinstance(seg["start"], (int, float))
            assert isinstance(seg["end"], (int, float))
