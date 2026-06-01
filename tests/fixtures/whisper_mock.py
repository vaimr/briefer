"""Mock WhisperEngine for testing.

Provides a fake Whisper transcription engine that returns canned
transcript results without requiring faster-whisper or ffmpeg.
"""

from unittest.mock import MagicMock


class FakeWhisperEngine:
    """Fake WhisperEngine for testing.

    Mimics whisper_engine.WhisperEngine interface:
    - transcribe(audio_path) -> (transcript: str, duration: float)

    Returns a canned transcript by default. Can be configured
    with custom transcripts via set_transcript().
    """

    DEFAULT_TRANSCRIPT = (
        "Speaker 1: Welcome to the meeting.\n"
        "Speaker 2: Thanks for joining. Let's discuss the project timeline.\n"
        "Speaker 1: The deadline is next Friday.\n"
        "Speaker 2: Agreed. I'll prepare the deliverables."
    )
    DEFAULT_DURATION = 120.0

    def __init__(
        self,
        model_name: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._custom_transcript: str | None = None
        self._custom_duration: float | None = None
        self._transcribe_calls: list[str] = []

    def set_transcript(self, text: str, duration: float = 120.0) -> None:
        """Set a custom transcript and duration for future calls."""
        self._custom_transcript = text
        self._custom_duration = duration

    def transcribe(self, audio_path: str) -> tuple[str, float]:
        """Transcribe audio and return (transcript, duration).

        Args:
            audio_path: Path to the audio file (ignored in fake).

        Returns:
            (transcript, duration_seconds)
        """
        self._transcribe_calls.append(audio_path)
        return (
            self._custom_transcript or self.DEFAULT_TRANSCRIPT,
            self._custom_duration or self.DEFAULT_DURATION,
        )

    def get_transcribe_calls(self) -> list[str]:
        """Return list of audio paths passed to transcribe()."""
        return list(self._transcribe_calls)

    def reset(self) -> None:
        """Reset all state."""
        self._transcribe_calls.clear()
        self._custom_transcript = None
        self._custom_duration = None


def mock_whisper_engine(
    model_name: str = "large-v3",
    transcript: str = DEFAULT_TRANSCRIPT,
    duration: float = 120.0,
):
    """Factory fixture to create a FakeWhisperEngine.

    Example:
        whisper = mock_whisper_engine()
        text, dur = whisper.transcribe("/tmp/audio.wav")
        assert dur == 120.0
    """
    engine = FakeWhisperEngine(model_name=model_name)
    if transcript:
        engine.set_transcript(transcript, duration)
    return engine
