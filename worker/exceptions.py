"""Briefer worker exceptions."""


class WorkerError(Exception):
    """Base exception for worker errors."""


class TranscriptionError(WorkerError):
    """Failed to transcribe audio."""


class LLMError(WorkerError):
    """Failed to call LLM API."""


class PDFGenerationError(WorkerError):
    """Failed to generate PDF."""


class RedisError(WorkerError):
    """Redis connection error."""


class TaskTimeoutError(WorkerError):
    """Task exceeded maximum duration."""


class AudioConversionError(WorkerError):
    """Failed to convert audio format."""
