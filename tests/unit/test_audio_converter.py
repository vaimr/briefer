"""Tests for worker.audio_converter — AudioConverter class."""

import os
import struct
import wave
from pathlib import Path

import pytest

from worker.audio_converter import AudioConverter


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_wav(path: Path, duration_sec: float, sample_rate: int,
               channels: int = 1, sampwidth: int = 2) -> Path:
    """Write a synthetic WAV file to *path*."""
    num_frames = int(sample_rate * duration_sec)
    samples = bytearray()
    for i in range(num_frames * channels):
        sample = 16000 * ((i % 3) - 1)
        sample = max(-32768, min(32767, sample))
        samples.extend(struct.pack("<h", sample))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(samples))
    return path


def _write_mp3(path: Path, duration_sec: float = 5) -> Path:
    """Create a minimal valid MP3 via ffmpeg from a synthetic WAV."""
    wav_tmp = path.with_suffix(".wav")
    _write_wav(wav_tmp, duration_sec, sample_rate=44100, channels=2)
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_tmp), "-c:a", "libmp3lame", str(path)],
        capture_output=True, text=True, check=True,
    )
    wav_tmp.unlink(missing_ok=True)
    return path


def _write_flac(path: Path, duration_sec: float = 5) -> Path:
    """Create a minimal valid FLAC via ffmpeg from a synthetic WAV."""
    wav_tmp = path.with_suffix(".wav")
    _write_wav(wav_tmp, duration_sec, sample_rate=24000, channels=1)
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_tmp), "-c:a", "flac", str(path)],
        capture_output=True, text=True, check=True,
    )
    wav_tmp.unlink(missing_ok=True)
    return path


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def converter():
    return AudioConverter()


# ── tests ────────────────────────────────────────────────────────────────────

class TestConvertWav16kMono:
    """WAV already at 16kHz mono should be returned as-is."""

    def test_returns_same_path(self, converter, tmp_path: Path):
        wav = tmp_path / "input.wav"
        _write_wav(wav, 5.0, sample_rate=16000, channels=1)
        result = converter.convert(wav)
        assert result == wav.resolve()

    def test_output_is_valid_wav(self, converter, tmp_path: Path):
        wav = tmp_path / "input.wav"
        _write_wav(wav, 5.0, sample_rate=16000, channels=1)
        result = converter.convert(wav)
        with wave.open(str(result), "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2


class TestConvertWav48kStereo:
    """WAV 48kHz stereo must be converted to 16kHz mono."""

    def test_converts_to_16k_mono(self, converter, tmp_path: Path):
        wav = tmp_path / "input.wav"
        _write_wav(wav, 5.0, sample_rate=48000, channels=2)
        result = converter.convert(wav)
        assert result != wav.resolve()
        assert result.suffix == ".wav"
        with wave.open(str(result), "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnchannels() == 1

    def test_preserves_duration(self, converter, tmp_path: Path):
        wav = tmp_path / "input.wav"
        _write_wav(wav, 10.0, sample_rate=48000, channels=2)
        result = converter.convert(wav)
        with wave.open(str(result), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
        assert abs(duration - 10.0) < 0.1


class TestConvertMp3:
    """MP3 must be converted to 16kHz mono WAV."""

    def test_converts_mp3_to_wav(self, converter, tmp_path: Path):
        mp3 = tmp_path / "input.mp3"
        _write_mp3(mp3, 5.0)
        result = converter.convert(mp3)
        assert result.suffix == ".wav"
        with wave.open(str(result), "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnchannels() == 1

    def test_output_sample_rate_is_16k(self, converter, tmp_path: Path):
        mp3 = tmp_path / "input.mp3"
        _write_mp3(mp3, 5.0)
        result = converter.convert(mp3)
        with wave.open(str(result), "rb") as wf:
            assert wf.getframerate() == 16000

    def test_output_channels_is_1(self, converter, tmp_path: Path):
        mp3 = tmp_path / "input.mp3"
        _write_mp3(mp3, 5.0)
        result = converter.convert(mp3)
        with wave.open(str(result), "rb") as wf:
            assert wf.getnchannels() == 1


class TestConvertFlac:
    """FLAC must be converted to 16kHz mono WAV."""

    def test_converts_flac_to_wav(self, converter, tmp_path: Path):
        flac = tmp_path / "input.flac"
        _write_flac(flac, 5.0)
        result = converter.convert(flac)
        assert result.suffix == ".wav"
        with wave.open(str(result), "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnchannels() == 1


class TestUnsupportedFormat:
    """Unsupported formats must raise ValueError."""

    def test_ogg_raises_value_error(self, converter, tmp_path: Path):
        ogg = tmp_path / "input.ogg"
        ogg.write_bytes(b"not a real ogg")
        with pytest.raises(ValueError, match="Unsupported audio format"):
            converter.convert(ogg)

    def test_txt_raises_value_error(self, converter, tmp_path: Path):
        txt = tmp_path / "input.txt"
        txt.write_text("not audio")
        with pytest.raises(ValueError, match="Unsupported audio format"):
            converter.convert(txt)

    def test_no_extension_raises_value_error(self, converter, tmp_path: Path):
        raw = tmp_path / "input"
        raw.write_bytes(b"no extension")
        with pytest.raises(ValueError, match="Unsupported audio format"):
            converter.convert(raw)


class TestCorruptedFile:
    """Corrupted files must raise ValueError."""

    def test_corrupted_wav_raises_value_error(self, converter, tmp_path: Path):
        wav = tmp_path / "corrupted.wav"
        wav.write_bytes(b"not a valid wav file at all")
        with pytest.raises(ValueError):
            converter.convert(wav)

    def test_nonexistent_file_raises_value_error(self, converter, tmp_path: Path):
        missing = tmp_path / "does_not_exist.wav"
        with pytest.raises(ValueError, match="Input file not found"):
            converter.convert(missing)


class TestOutputValidation:
    """Output WAV must pass wave module validation."""

    def test_output_wav_is_valid(self, converter, tmp_path: Path):
        wav = tmp_path / "input.wav"
        _write_wav(wav, 5.0, sample_rate=48000, channels=2)
        result = converter.convert(wav)
        # _validate_wav is called internally; if we reach here it passed.
        # Confirm independently:
        with wave.open(str(result), "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2

    def test_convert_preserves_duration(self, converter, tmp_path: Path):
        wav = tmp_path / "input.wav"
        _write_wav(wav, 10.0, sample_rate=48000, channels=2)
        result = converter.convert(wav)
        with wave.open(str(result), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
        assert abs(duration - 10.0) < 0.1
