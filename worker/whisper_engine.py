"""Whisper transcription engine."""

import subprocess
from faster_whisper import WhisperModel


class WhisperEngine:
    """Обёртка над faster-whisper для транскрибации аудио."""

    def __init__(self, model_name: str, device: str = "cpu", compute_type: str = "int8"):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str) -> tuple[str, float]:
        """Конвертация аудио в WAV и транскрибация.

        Returns:
            (transcript, duration_seconds)
        """
        wav_path = audio_path.rsplit(".", 1)[0] + ".wav"
        subprocess.run(
            ["ffmpeg", "-i", audio_path, "-ar", "16000", "-ac", "1", "-y", wav_path],
            check=True, capture_output=True,
        )

        segments, info = self.model.transcribe(
            wav_path, beam_size=5, vad_filter=True, language=None,
        )
        duration = info.duration

        transcript_lines = []
        for s in segments:
            speaker = getattr(s, "speaker", None)
            speaker_str = str(speaker) if speaker is not None else "?"
            transcript_lines.append(f"Speaker {speaker_str}: {s.text}")

        return "\n".join(transcript_lines), duration
