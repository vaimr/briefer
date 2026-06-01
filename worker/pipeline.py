"""Task processing pipeline for transcription workflows."""

import datetime
import logging
import os
from pathlib import Path

from worker.audio import convert_to_wav
from worker.llm_client import LLMClient
from worker.pdf_generator import PDFGenerator
from worker.transcriber import transcribe_wav

logger = logging.getLogger(__name__)


def parse_task(task_str: str) -> tuple[str, str]:
    """Parse a task string into (room_id, audio_path).

    Given: a task string in "room_id|audio_path" format
    When: the string contains exactly one pipe separator
    And: both parts are non-empty
    Then: return (room_id, audio_path) tuple

    When: the string has no pipe
    Then: raise ValueError
    When: room_id is empty
    Then: raise ValueError
    When: audio_path is empty
    Then: raise ValueError
    """
    parts = task_str.split("|", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid task format, expected 'room_id|path': {task_str!r}"
        )
    room_id, audio_path = parts
    if not room_id or not audio_path:
        raise ValueError(f"Task parts cannot be empty: {task_str!r}")
    return room_id, audio_path


def process_transcription_task(task_str: str, config) -> dict:
    """Process a transcription task end-to-end.

    Given: a task string and a config object
    When: the audio file exists
    And: conversion + transcription succeed
    Then: return dict with room_id, audio_path, transcript, segments,
          duration, wav_path

    When: audio file does not exist
    Then: raise FileNotFoundError
    When: task string is invalid
    Then: ValueError propagates
    """
    room_id, audio_path = parse_task(task_str)

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    logger.info("[%s] START_TRANSCRIPTION: %s", room_id, audio_path)

    wav_path, duration = convert_to_wav(audio_path, config.data_dir)
    transcript, segments = transcribe_wav(wav_path, config.whisper_model)

    if not transcript:
        logger.warning("[%s] Empty transcript for %s", room_id, audio_path)

    logger.info(
        "[%s] TRANSCRIPTION_COMPLETE: %.1fs, %d chars, %d segments",
        room_id,
        duration,
        len(transcript),
        len(segments),
    )

    return {
        "room_id": room_id,
        "audio_path": audio_path,
        "transcript": transcript,
        "segments": segments,
        "duration": duration,
        "wav_path": wav_path,
    }


def process_transcription(
    transcript_text: str,
    api_url: str,
    model_name: str,
    data_dir: str,
) -> Path:
    """Generate a summary PDF from transcription text.

    Given: non-empty transcript text, LLM API URL, model name, and data directory
    When: all stages succeed
    Then: return Path to the generated PDF in data/summaries/<timestamp>/

    When: transcript_text is empty or whitespace-only
    Then: raise ValueError
    When: LLM returns empty summary
    Then: raise ValueError
    """
    if not transcript_text or not transcript_text.strip():
        raise ValueError("transcript_text must not be empty or whitespace")

    # Stage 1: LLM summary
    llm_client = LLMClient(api_url, model_name)
    logger.info("LLM summary generation started")
    summary = llm_client.summarize(transcript_text)
    logger.info("LLM summary generated")

    if not summary or not summary.strip():
        raise ValueError("LLM returned empty summary")

    # Stage 2: PDF generation
    pdf_generator = PDFGenerator()
    output_dir = (
        Path(data_dir) / "summaries" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = output_dir / "transcription.pdf"
    pdf_file = pdf_generator.generate(transcript_text, summary, pdf_path)
    logger.info("PDF generated: %s", pdf_file)

    return pdf_file
