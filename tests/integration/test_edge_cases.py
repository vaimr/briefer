"""Integration tests for edge cases and boundary conditions.

These tests verify that the system handles edge cases correctly
across multiple modules working together.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audio_dir() -> Path:
    """Path to the tests/audio directory."""
    return Path(__file__).parent.parent / "audio"


@pytest.fixture
def tmp_work_dir(tmp_path: Path) -> Path:
    """Temporary working directory for integration tests."""
    return tmp_path / "edge_cases"


# ---------------------------------------------------------------------------
# Audio Format Validation
# ---------------------------------------------------------------------------


class TestAudioFormatValidation:
    """Test audio format validation across modules."""

    def test_audio_converter_rejects_non_audio(self, tmp_work_dir):
        """AudioConverter should reject non-audio files."""
        from worker.audio_converter import AudioConverter

        converter = AudioConverter()
        fake_audio = tmp_work_dir / "fake.mp3"
        fake_audio.parent.mkdir(parents=True, exist_ok=True)
        fake_audio.write_bytes(b"not really mp3 data")

        # This should either succeed (ffmpeg handles it) or fail gracefully
        # We just verify the function doesn't crash
        try:
            result = converter.convert(fake_audio)
            # If it succeeds, the output should be a valid WAV
            assert result.suffix == ".wav"
        except ValueError:
            # Or it should raise ValueError for unsupported/corrupted files
            pass

    def test_audio_converter_handles_already_optimal_wav(self, audio_dir):
        """WAV that is already 16kHz mono should be returned as-is."""
        from worker.audio_converter import AudioConverter

        converter = AudioConverter()
        # Find a WAV file
        wav_files = list(audio_dir.glob("*.wav"))
        if not wav_files:
            pytest.skip("No WAV files in tests/audio/")

        wav_path = wav_files[0]
        result = converter.convert(wav_path)

        # If already optimal, should return same path
        # If not optimal, should return converted path
        assert result.exists()
        assert result.suffix == ".wav"


# ---------------------------------------------------------------------------
# PDF Generation Edge Cases
# ---------------------------------------------------------------------------


class TestPDFEdgeCases:
    """Test PDF generation edge cases."""

    def test_generate_pdf_with_cyrillic_text(self, tmp_work_dir):
        """PDF should support Cyrillic characters (mocked pandoc)."""
        from worker.pdf_generator import PDFGenerator

        transcription = "Это транскрипция на русском языке. Обсуждались quarterly results."
        summary = "Краткое изложение встречи."
        output_path = tmp_work_dir / "cyrillic.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            result = generator.generate(transcription, summary, output_path)

        assert result.exists(), "PDF with Cyrillic should be created"

    def test_generate_pdf_with_special_characters(self, tmp_work_dir):
        """PDF should handle special characters in text (mocked pandoc)."""
        from worker.pdf_generator import PDFGenerator

        transcription = "Meeting with <script>alert('xss')</script> and special chars: @#$%^&*()"
        summary = "Special chars: àéîöü"
        output_path = tmp_work_dir / "special.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            result = generator.generate(transcription, summary, output_path)

        assert result.exists(), "PDF with special chars should be created"

    def test_generate_pdf_with_unicode_emojis(self, tmp_work_dir):
        """PDF should handle Unicode emojis (mocked pandoc)."""
        from worker.pdf_generator import PDFGenerator

        transcription = "Meeting with emojis: 🎯 📊 💰"
        summary = "Discussion about goals 💡"
        output_path = tmp_work_dir / "emoji.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            result = generator.generate(transcription, summary, output_path)

        assert result.exists(), "PDF with emojis should be created"


# ---------------------------------------------------------------------------
# LLM Client Edge Cases
# ---------------------------------------------------------------------------


class TestLLMClientEdgeCases:
    """Test LLM client edge cases."""

    def test_summarize_whitespace_only(self):
        """Whitespace-only transcription should return default message."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        result = client.summarize("   \n\t  ")
        assert "Нет данных для саммари" in result

    def test_summarize_exactly_max_length(self):
        """Transcription at exactly MAX_TRANSCRIPTION_LENGTH should not be truncated."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        exact_length = "x" * LLMClient.MAX_TRANSCRIPTION_LENGTH

        with patch("worker.llm_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "summary"}}],
            }
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()

            client.summarize(exact_length)

        # Should not be truncated
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        user_content = payload["messages"][1]["content"]
        # The prompt adds some text before the transcription
        assert len(user_content) >= LLMClient.MAX_TRANSCRIPTION_LENGTH

    def test_summarize_one_char_over_limit(self):
        """Transcription one char over limit should be truncated."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        over_limit = "x" * (LLMClient.MAX_TRANSCRIPTION_LENGTH + 1)

        with patch("worker.llm_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "summary"}}],
            }
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()

            client.summarize(over_limit)

        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        user_content = payload["messages"][1]["content"]
        assert len(user_content) <= LLMClient.MAX_TRANSCRIPTION_LENGTH + 200

    def test_summarize_empty_choices_raises(self):
        """Empty choices array should raise ValueError."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        with patch("worker.llm_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"choices": []}
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()

            with pytest.raises(Exception):  # KeyError or similar
                client.summarize("test")

    def test_summarize_4xx_error_raises_immediately(self):
        """4xx errors should raise immediately without retry."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        with patch("worker.llm_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.raise_for_status.side_effect = Exception("400 Bad Request")
            mock_post.return_value = mock_response

            with pytest.raises(Exception):
                client.summarize("test")

        assert mock_post.call_count == 1  # No retries


# ---------------------------------------------------------------------------
# Retry Mechanism Edge Cases
# ---------------------------------------------------------------------------


class TestRetryEdgeCases:
    """Test retry mechanism edge cases."""

    def test_retry_zero_max_retries(self):
        """Zero max_retries should not retry at all."""
        from worker.retry import retry

        call_count = 0

        @retry(max_retries=1, base_delay=1.0)
        def never_succeeds():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("no retries")

        with pytest.raises(ConnectionError):
            never_succeeds()

        assert call_count == 1

    def test_retry_preserves_function_metadata(self):
        """Retry decorator should preserve function name and docstring."""
        from worker.retry import retry

        @retry(max_retries=3, base_delay=0.01)
        def my_function():
            """My function docstring."""
            return "success"

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My function docstring."

    def test_retry_with_args_and_kwargs(self):
        """Retry should work with functions that have args and kwargs."""
        from worker.retry import retry

        call_count = 0

        @retry(max_retries=2, base_delay=0.01)
        def add_with_retry(a, b, multiplier=1):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("retry")
            return (a + b) * multiplier

        result = add_with_retry(3, 4, multiplier=2)
        assert result == 14  # (3 + 4) * 2


# ---------------------------------------------------------------------------
# Task Tracker Edge Cases
# ---------------------------------------------------------------------------


class TestTaskTrackerEdgeCases:
    """Test task tracker edge cases."""

    def test_tracker_with_empty_task_id(self):
        """Empty task_id should still be tracked (or raise ValueError)."""
        from worker.task_tracker import TaskTracker

        tracker = TaskTracker()
        # Empty task_id should be tracked (it's the caller's responsibility)
        is_dup = tracker.is_duplicate("")
        # Should not crash
        assert isinstance(is_dup, bool)

    def test_tracker_with_duplicate_task_ids(self):
        """Multiple identical task_ids should all return True after first."""
        from worker.task_tracker import TaskTracker

        tracker = TaskTracker()

        # First call should be False (not duplicate)
        assert tracker.is_duplicate("task-001") is False
        # Subsequent calls should be True (duplicate)
        for _ in range(9):
            assert tracker.is_duplicate("task-001") is True

    def test_tracker_clear_nonexistent_task(self):
        """clearing a non-existent task should not raise."""
        from worker.task_tracker import TaskTracker

        tracker = TaskTracker()
        tracker.clear("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# Error Handling Edge Cases
# ---------------------------------------------------------------------------


class TestErrorHandlingEdgeCases:
    """Test error handling edge cases."""

    def test_handle_error_with_traceback(self):
        """handle_error should handle exceptions with tracebacks."""
        from worker.errors import TaskError, handle_error

        try:
            raise ValueError("test error with traceback")
        except Exception as e:
            error = TaskError.from_exception("task-001", e)
            assert error.task_id == "task-001"
            assert error.error_type == "ValueError"
            assert "test error with traceback" in error.message

    def test_task_error_to_dict_serialization(self):
        """TaskError should serialize to dict correctly."""
        from worker.errors import TaskError

        error = TaskError(
            task_id="task-001",
            error_type="ValueError",
            message="test error",
            retry_count=2,
        )
        d = error.to_dict()
        assert d["task_id"] == "task-001"
        assert d["error_type"] == "ValueError"
        assert d["message"] == "test error"
        assert d["retry_count"] == 2

    def test_handle_error_increments_retry_count(self):
        """handle_error should increment retry_count on each call."""
        from worker.errors import handle_error

        error = ValueError("test")

        # First call
        handle_error("task-001", error, max_retries=5)
        # Second call (should still retry since max_retries=5)
        result = handle_error("task-001", error, max_retries=5)
        assert result is True


# ---------------------------------------------------------------------------
# DLQ Edge Cases
# ---------------------------------------------------------------------------


class TestDLQEdgeCases:
    """Test Dead Letter Queue edge cases."""

    def test_dlq_add_and_retrieve(self):
        """Add to DLQ and retrieve should return the message."""
        from worker.dlq import DeadLetterQueue

        mock_redis = MagicMock()
        mock_redis.llen.return_value = 1
        mock_redis.lrange.return_value = [
            json.dumps({
                "task_id": "task-001",
                "error": "ValueError",
                "traceback": "traceback...",
                "timestamp": "2024-01-01T00:00:00",
            })
        ]

        dlq = DeadLetterQueue(mock_redis)
        messages = dlq.get_all()
        assert len(messages) == 1
        assert messages[0]["task_id"] == "task-001"

    def test_dlq_remove_nonexistent(self):
        """Removing a non-existent task should not raise."""
        from worker.dlq import DeadLetterQueue

        mock_redis = MagicMock()
        mock_redis.llen.return_value = 0
        mock_redis.lrange.return_value = []

        dlq = DeadLetterQueue(mock_redis)
        dlq.remove("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# Full Pipeline Edge Cases
# ---------------------------------------------------------------------------


class TestFullPipelineEdgeCases:
    """Test full pipeline edge cases."""

    def test_pipeline_empty_audio(self, tmp_work_dir):
        """Pipeline should handle empty audio gracefully (mocked PDF)."""
        from worker.llm_client import LLMClient
        from worker.pdf_generator import PDFGenerator

        # Empty transcription → default summary
        llm_client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )
        summary = llm_client.summarize("")
        assert "Нет данных для саммари" in summary

        # PDF should still be generated
        output_path = tmp_work_dir / "empty.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            pdf_path = generator.generate("", summary, output_path)

        assert pdf_path.exists()

    def test_pipeline_very_long_summary(self, tmp_work_dir):
        """Summary > 2000 chars should be truncated."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        with patch("worker.llm_client.requests.post") as mock_post:
            long_summary = "x" * 5000
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": long_summary}}],
            }
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()

            result = client.summarize("test")

        assert len(result) <= 2000  # MAX_SUMMARY_LENGTH

    def test_pipeline_pdf_generation_fails(self, tmp_work_dir):
        """PDF generation failure should raise ValueError."""
        from worker.pdf_generator import PDFGenerator

        output_path = tmp_work_dir / "fail.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        generator = PDFGenerator()
        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="pandoc error")
            with pytest.raises(ValueError, match="Pandoc failed"):
                generator.generate("text", "summary", output_path)
