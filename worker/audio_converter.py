"""Audio converter module — transcode supported formats to 16kHz mono WAV for Whisper."""

import logging
import subprocess
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioConverter:
    """Convert audio files to 16kHz mono WAV suitable for Whisper transcription."""

    SUPPORTED_FORMATS = {".wav", ".mp3", ".flac"}
    OUTPUT_SAMPLE_RATE = 16000
    OUTPUT_CHANNELS = 1

    def convert(self, input_path: Path) -> Path:
        """Convert *input_path* to 16kHz mono WAV.

        Args:
            input_path: Path to the input audio file.

        Returns:
            Path to the output WAV file. If the input is already an optimal
            16kHz mono WAV the same path is returned.

        Raises:
            ValueError: If the format is unsupported, the file is corrupted,
                or ffmpeg fails.
        """
        suffix = input_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported audio format: {suffix!r}")

        input_path = Path(input_path).resolve()

        if not input_path.exists():
            raise ValueError(f"Input file not found: {input_path}")

        # Already optimal — skip conversion
        if self._is_already_optimal(input_path):
            logger.info("File already optimal (16kHz mono WAV): %s", input_path)
            return input_path

        stem = input_path.stem
        if input_path.suffix.lower() == ".wav":
            output_path = input_path.with_name(f"{stem}_converted.wav")
        else:
            output_path = input_path.with_suffix(".wav")
        logger.info("Converting %s → %s (16kHz mono WAV)", input_path, output_path)

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-ar", str(self.OUTPUT_SAMPLE_RATE),
            "-ac", str(self.OUTPUT_CHANNELS),
            "-c:a", "pcm_s16le",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            raise ValueError("ffmpeg is not installed or not in PATH")
        except subprocess.TimeoutExpired:
            raise ValueError("ffmpeg conversion timed out after 120 s")

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            raise ValueError(f"ffmpeg failed (rc={result.returncode}): {stderr}")

        if not output_path.exists():
            raise ValueError("ffmpeg reported success but output file not created")

        self._validate_wav(output_path)
        logger.info("Conversion complete: %s", output_path)
        return output_path

    def _is_already_optimal(self, path: Path) -> bool:
        """Return True if *path* is already a 16kHz mono WAV."""
        if path.suffix.lower() != ".wav":
            return False
        try:
            with wave.open(str(path), "rb") as wf:
                if wf.getframerate() != self.OUTPUT_SAMPLE_RATE:
                    return False
                if wf.getnchannels() != self.OUTPUT_CHANNELS:
                    return False
                return True
        except (wave.Error, OSError) as exc:
            logger.debug("Cannot read WAV header for opt check: %s", exc)
            return False

    def _validate_wav(self, path: Path) -> None:
        """Validate that *path* is a 16kHz mono WAV.

        Raises:
            ValueError: If the WAV does not match expected parameters.
        """
        try:
            with wave.open(str(path), "rb") as wf:
                if wf.getframerate() != self.OUTPUT_SAMPLE_RATE:
                    raise ValueError(
                        f"Output sample rate {wf.getframerate()} != "
                        f"{self.OUTPUT_SAMPLE_RATE}"
                    )
                if wf.getnchannels() != self.OUTPUT_CHANNELS:
                    raise ValueError(
                        f"Output channels {wf.getnchannels()} != "
                        f"{self.OUTPUT_CHANNELS}"
                    )
                if wf.getsampwidth() != 2:
                    raise ValueError(
                        f"Output sampwidth {wf.getsampwidth()} != 2 (16-bit)"
                    )
        except wave.Error as exc:
            raise ValueError(f"Output WAV is invalid: {exc}") from exc
