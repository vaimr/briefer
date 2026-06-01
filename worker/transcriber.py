"""Whisper transcription module."""

import logging
import wave
from pathlib import Path

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class Transcriber:
    """Обёртка над faster-whisper для транскрибации аудио."""

    def __init__(
        self,
        model_name: str = "large-v3",
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.device = device
        logger.info(
            "Initializing Transcriber: model=%s, device=%s, compute_type=int8",
            model_name,
            device,
        )
        try:
            self.model = WhisperModel(
                model_name,
                device=device,
                compute_type="int8",
            )
        except Exception as e:
            logger.error("Failed to load Whisper model: %s", e)
            raise ValueError(f"Failed to load Whisper model: {e}") from e
        logger.info("Transcriber initialized successfully")

    def transcribe(self, file_path: Path) -> dict:
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            raise FileNotFoundError(f"File not found: {file_path}")

        duration = self._get_duration(file_path)
        logger.info("Audio duration: %.2f sec for %s", duration, file_path)

        if duration == 0:
            logger.error("Empty audio file: %s", file_path)
            raise ValueError(f"Empty audio file: {file_path}")
        if duration > 30 * 60:
            logger.error(
                "Audio too long: %.2f sec > 1800 sec for %s",
                duration,
                file_path,
            )
            raise ValueError(
                f"Audio file too long: {duration:.0f}s > 30min",
            )

        logger.info("Transcribing: %s (language=ru, beam_size=5)", file_path)
        segments, info = self.model.transcribe(
            str(file_path),
            language="ru",
            beam_size=5,
        )

        segments_list, text_parts = [], []
        for seg in segments:
            segments_list.append(
                {"text": seg.text, "start": seg.start, "end": seg.end},
            )
            text_parts.append(seg.text)

        logger.info(
            "Transcription complete: %.2f sec, %d segments",
            duration,
            len(segments_list),
        )

        result = {
            "text": "".join(text_parts).strip(),
            "segments": segments_list,
            "duration": duration,
            "language": info.language,
        }
        logger.debug("Transcription result: %d segments, %d chars",
                      len(segments_list), len(result["text"]))
        return result

    def _get_duration(self, file_path: Path) -> float:
        with wave.open(str(file_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
        duration = frames / rate if rate > 0 else 0.0
        logger.debug("Duration calc: %d frames / %d fps = %.4f sec",
                      frames, rate, duration)
        return duration


_model_instance: Transcriber | None = None


def _get_model_instance(model_name: str = "large-v3") -> Transcriber:
    global _model_instance
    if _model_instance is None:
        _model_instance = Transcriber(model_name=model_name)
    return _model_instance


def transcribe_wav(
    wav_path: str, model_name: str = "large-v3"
) -> tuple[str, list[dict]]:
    """Transcribe a WAV file and return (full_text, segments).

    Given: a path to a WAV file and optional model name
    When: the file exists and is valid
    Then: return (full_text, segments) tuple

    When: file does not exist
    Then: FileNotFoundError
    When: audio is empty or too long
    Then: ValueError
    """
    file_path = Path(wav_path)
    model = _get_model_instance(model_name)
    result = model.transcribe(file_path)

    text = result["text"]
    segments = result["segments"]
    logger.info(
        "transcribe_wav: %.2fs -> %d chars, %d segments",
        result["duration"],
        len(text),
        len(segments),
    )
    return text, segments
