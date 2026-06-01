"""Audio conversion utilities — ffmpeg-based WAV conversion."""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_duration(path: str) -> float:
    """Extract audio duration in seconds via ffprobe.

    Given: a path to an audio file
    When: ffprobe can read the file
    Then: return duration as float
    When: ffprobe fails
    Then: raise subprocess.CalledProcessError
    """
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def convert_to_wav(audio_path: str, output_dir: str) -> tuple[str, float]:
    """Convert an audio file to WAV (16kHz mono) via ffmpeg.

    Given: a path to an audio file (any format) and an output directory
    When: the audio file exists
    And: ffmpeg is available
    Then: WAV file is created in output_dir with 16kHz mono format
    When: the audio file does not exist
    Then: FileNotFoundError is raised
    When: ffmpeg fails
    Then: RuntimeError is raised with stderr details
    When: the resulting WAV is empty
    Then: FileNotFoundError is raised
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    wav_path = str(output_dir / f"{Path(audio_path).stem}.wav")

    cmd = [
        "ffmpeg", "-i", audio_path,
        "-ar", "16000", "-ac", "1",
        "-y", wav_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg failed: %s", e.stderr)
        raise RuntimeError(f"ffmpeg conversion failed: {e.stderr}") from e

    if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
        raise FileNotFoundError(f"WAV file not created or empty: {wav_path}")

    duration = _get_duration(wav_path)
    logger.info("Converted %s -> %s (%.1fs)", audio_path, wav_path, duration)
    return wav_path, duration
