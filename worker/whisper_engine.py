"""Whisper transcription engine."""

import logging
import os
import subprocess
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


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
        import os
        file_size = os.path.getsize(audio_path)
        logger.info("Transcribing: %s (size=%d bytes)", audio_path, file_size)

        wav_path = audio_path.rsplit(".", 1)[0] + ".wav"
        tmp_path = wav_path + ".tmp.wav"
        result = subprocess.run(
            ["ffmpeg", "-i", audio_path, "-ar", "16000", "-ac", "1", "-y", tmp_path],
            capture_output=True, timeout=300,
        )
        if result.returncode != 0:
            logger.error("ffmpeg failed: rc=%d stderr=%s", result.returncode, result.stderr.decode()[:500])
            raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()}")
        os.replace(tmp_path, wav_path)

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
