"""Pytest fixtures для тестов бота и воркера."""

import os
import pytest

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio")


@pytest.fixture
def audio_files():
    """Возвращает список тестовых аудио файлов."""
    files = []
    if os.path.exists(AUDIO_DIR):
        for f in os.listdir(AUDIO_DIR):
            if f.endswith(".wav"):
                files.append(os.path.join(AUDIO_DIR, f))
    return files


@pytest.fixture
def short_audio(audio_files):
    """Возвращает путь к короткому аудио файлу."""
    for f in audio_files:
        if "short" in f:
            return f
    return None


@pytest.fixture
def long_audio(audio_files):
    """Возвращает путь к длинному аудио файлу."""
    for f in audio_files:
        if "long" in f:
            return f
    return None


@pytest.fixture
def risk_audio(audio_files):
    """Возвращает путь к аудио файлу с рисками."""
    for f in audio_files:
        if "risk" in f:
            return f
    return None
