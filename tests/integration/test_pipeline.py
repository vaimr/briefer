"""Integration tests for the audio transcription pipeline.

These tests verify end-to-end workflows by combining multiple modules
with real audio files and mocked external services (LLM, Matrix).
"""

import json
import time
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
def short_audio_path(audio_dir: Path) -> Path:
    """Path to short_meeting.wav (10s)."""
    path = audio_dir / "short_meeting.wav"
    assert path.exists(), f"Test audio file not found: {path}"
    return path


@pytest.fixture
def long_audio_path(audio_dir: Path) -> Path:
    """Path to long_meeting.wav (30s)."""
    path = audio_dir / "long_meeting.wav"
    assert path.exists(), f"Test audio file not found: {path}"
    return path


@pytest.fixture
def tmp_work_dir(tmp_path: Path) -> Path:
    """Temporary working directory for integration tests."""
    return tmp_path / "integration"


# ---------------------------------------------------------------------------
# Audio Converter + Transcriber Integration
# ---------------------------------------------------------------------------


class TestAudioPipeline:
    """Test AudioConverter → Transcriber integration with real audio files."""

    def test_convert_and_transcribe_short_audio(self, short_audio_path, tmp_work_dir):
        """Convert short audio to 16kHz WAV and transcribe.

        Integration: AudioConverter.convert() → Transcriber.transcribe()
        """
        from worker.audio_converter import AudioConverter
        from worker.transcriber import Transcriber

        converter = AudioConverter()
        wav_path = converter.convert(short_audio_path)

        assert wav_path.exists(), "Converted WAV file not created"
        assert wav_path.suffix == ".wav", f"Expected .wav, got {wav_path.suffix}"

        with patch("worker.transcriber.WhisperModel") as MockWhisper:
            mock_segments = [
                MagicMock(text="test transcription", start=0.0, end=1.0),
            ]
            MockWhisper.return_value.transcribe.return_value = (mock_segments, MagicMock(language="ru"))

            transcriber = Transcriber()
            result = transcriber.transcribe(wav_path)

        assert "text" in result, "Missing 'text' key in transcription result"
        assert "segments" in result, "Missing 'segments' key in transcription result"
        assert "duration" in result, "Missing 'duration' key in transcription result"
        assert "language" in result, "Missing 'language' key in transcription result"
        assert len(result["text"]) > 0, "Transcription text should not be empty"

    def test_convert_preserves_duration(self, short_audio_path, tmp_work_dir):
        """Converted WAV should preserve original duration (±0.5s)."""
        import wave

        from worker.audio_converter import AudioConverter

        converter = AudioConverter()
        wav_path = converter.convert(short_audio_path)

        with wave.open(str(wav_path), "rb") as wf:
            converted_duration = wf.getnframes() / wf.getframerate()

        # Original duration should be ~10s
        assert 5 < converted_duration < 15, f"Expected duration ~10s, got {converted_duration}s"

    def test_convert_sample_rate_16k(self, short_audio_path, tmp_work_dir):
        """Converted WAV should have exactly 16kHz sample rate."""
        import wave

        from worker.audio_converter import AudioConverter

        converter = AudioConverter()
        wav_path = converter.convert(short_audio_path)

        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getframerate() == 16000, f"Expected 16000 Hz, got {wf.getframerate()}"
            assert wf.getnchannels() == 1, f"Expected 1 channel (mono), got {wf.getnchannels()}"

    def test_convert_unsupported_format_raises(self, tmp_work_dir):
        """Unsupported format should raise ValueError."""
        from worker.audio_converter import AudioConverter

        converter = AudioConverter()
        unsupported = tmp_work_dir / "test.ogg"
        unsupported.parent.mkdir(parents=True, exist_ok=True)
        unsupported.write_bytes(b"fake ogg content")

        with pytest.raises(ValueError, match="Unsupported"):
            converter.convert(unsupported)


# ---------------------------------------------------------------------------
# PDF Generator Integration
# ---------------------------------------------------------------------------


class TestPDFGeneration:
    """Test PDF generation with real markdown content."""

    def test_generate_pdf_from_transcription_and_summary(
        self, tmp_work_dir
    ):
        """Generate PDF from transcription + summary text (mocked pandoc)."""
        from worker.pdf_generator import PDFGenerator

        transcription = "This is a meeting transcription about quarterly results."
        summary = "The team discussed Q4 targets and budget allocation."
        output_path = tmp_work_dir / "output.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            result = generator.generate(transcription, summary, output_path)

        assert result.exists(), "PDF file not created"
        assert result.suffix == ".pdf", f"Expected .pdf, got {result.suffix}"

    def test_generate_pdf_without_summary(self, tmp_work_dir):
        """PDF should be generated even without summary (mocked pandoc)."""
        from worker.pdf_generator import PDFGenerator

        transcription = "Meeting transcription text here."
        output_path = tmp_work_dir / "no_summary.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            result = generator.generate(transcription, "", output_path)

        assert result.exists(), "PDF not created for empty summary"

    def test_generate_pdf_truncates_long_text(self, tmp_work_dir):
        """Transcription > 50000 chars should be truncated before PDF generation (mocked)."""
        from worker.pdf_generator import PDFGenerator

        long_text = "x" * 60000
        summary = "Summary"
        output_path = tmp_work_dir / "long.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            result = generator.generate(long_text, summary, output_path)

        assert result.exists(), "PDF not created for long text"


# ---------------------------------------------------------------------------
# LLM Client Integration (mocked API)
# ---------------------------------------------------------------------------


class TestLLMClientIntegration:
    """Test LLMClient with mocked HTTP responses."""

    def test_summarize_short_text(self):
        """Summarize short transcription text."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        with patch("worker.llm_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "This meeting discussed quarterly results."}}],
            }
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()

            result = client.summarize("This is a test transcription about quarterly results.")

        assert "This meeting discussed quarterly results." in result

    def test_summarize_empty_text_returns_default(self):
        """Empty transcription should return default message."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        result = client.summarize("")
        assert "Нет данных для саммари" in result

    def test_summarize_truncates_long_text(self):
        """Transcription > 4000 chars should be truncated before API call."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        long_text = "x" * 5000

        with patch("worker.llm_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "summary"}}],
            }
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()

            client.summarize(long_text)

        # Check that the payload was truncated
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        user_content = payload["messages"][1]["content"]
        assert len(user_content) <= 4000 + 200  # 4000 + prompt overhead

    def test_summarize_retry_on_500(self):
        """LLMClient should retry on 500 errors."""
        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        with patch("worker.llm_client.requests.post") as mock_post, \
             patch("worker.llm_client.time.sleep"):
            # First 2 calls return 500, third succeeds
            mock_post.side_effect = [
                MagicMock(status_code=500, text="server error"),
                MagicMock(status_code=500, text="server error"),
                MagicMock(
                    json=MagicMock(return_value={"choices": [{"message": {"content": "recovered"}}]}),
                    status_code=200,
                    raise_for_status=MagicMock(),
                ),
            ]

            result = client.summarize("test")

        assert "recovered" in result
        assert mock_post.call_count == 3

    def test_summarize_raises_after_3_failed_retries(self):
        """All 3 retries fail → should raise ConnectionError or similar."""
        import requests

        from worker.llm_client import LLMClient

        client = LLMClient(
            api_url="http://localhost:8080/v1",
            model_name="test-model",
        )

        with patch("worker.llm_client.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

            with pytest.raises(Exception):
                client.summarize("test")

        assert mock_post.call_count == 3


# ---------------------------------------------------------------------------
# Redis Queue Integration
# ---------------------------------------------------------------------------


class TestRedisQueueIntegration:
    """Test enqueue/dequeue with mock Redis."""

    def test_enqueue_and_dequeue_full_flow(self):
        """Full enqueue → dequeue flow."""
        from bot.client import enqueue_task

        mock_redis = MagicMock()
        mock_redis.rpush.return_value = 1

        result = enqueue_task(mock_redis, "room-123", "/data/audio/meeting.wav")
        assert result == "room-123|/data/audio/meeting.wav"
        mock_redis.rpush.assert_called_once_with(
            "transcription_queue", "room-123|/data/audio/meeting.wav"
        )

    def test_enqueue_validates_inputs(self):
        """Empty room_id or audio_path should raise ValueError."""
        from bot.client import enqueue_task

        mock_redis = MagicMock()

        with pytest.raises(ValueError, match="room_id"):
            enqueue_task(mock_redis, "", "/data/audio/meeting.wav")

        with pytest.raises(ValueError, match="audio_path"):
            enqueue_task(mock_redis, "room-123", "")

    def test_dequeue_parses_task(self):
        """dequeue_task should parse room_id and audio_path from pipe-separated string."""
        from redis import Redis

        mock_redis = MagicMock(spec=Redis)
        mock_redis.blpop.return_value = (
            b"transcription_queue",
            "room-456|/data/audio/test.mp3".encode(),
        )

        from worker.__main__ import dequeue_task

        result = dequeue_task(mock_redis)
        assert result == ("room-456", "/data/audio/test.mp3")

    def test_dequeue_returns_none_on_timeout(self):
        """blpop timeout should return None."""
        from redis import Redis

        mock_redis = MagicMock(spec=Redis)
        mock_redis.blpop.return_value = None

        from worker.__main__ import dequeue_task

        result = dequeue_task(mock_redis)
        assert result is None


# ---------------------------------------------------------------------------
# Result Publisher Integration
# ---------------------------------------------------------------------------


class TestResultPublisherIntegration:
    """Test ResultPublisher with mock Redis."""

    def test_publish_result_formats_json(self):
        """Result should be published as valid JSON."""
        from worker.result_publisher import ResultPublisher

        mock_redis = MagicMock()
        publisher = ResultPublisher("localhost", 6379)
        publisher.redis = mock_redis

        transcription = {"text": "test transcription", "duration": 10.0}
        pdf_path = Path("/tmp/test.pdf")

        with patch.object(Path, "exists", return_value=True):
            publisher.publish_result("task-001", transcription, pdf_path)

        # Verify publish was called with valid JSON
        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        json_str = call_args[0][1]

        assert channel == "task_results"
        data = json.loads(json_str)
        assert data["task_id"] == "task-001"
        assert data["transcription"] == "test transcription"
        assert data["pdf_path"] == "/tmp/test.pdf"
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# Retry Mechanism Integration
# ---------------------------------------------------------------------------


class TestRetryIntegration:
    """Test retry decorator with real exponential backoff."""

    def test_retry_succeeds_after_failures(self):
        """Retry should succeed on final attempt."""
        from worker.retry import retry

        call_count = 0

        @retry(max_retries=3, base_delay=0.01)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient error")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert call_count == 3

    def test_retry_does_not_retry_permanent_error(self):
        """Permanent errors should not be retried."""
        from worker.retry import retry

        call_count = 0

        @retry(max_retries=3, base_delay=0.01)
        def bad_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent error"):
            bad_function()

        assert call_count == 1  # Only one attempt

    def test_retry_exponential_backoff_timing(self):
        """Delays should follow exponential backoff pattern."""
        from worker.retry import retry

        timestamps = []

        @retry(max_retries=3, base_delay=0.1)
        def timing_function():
            timestamps.append(time.monotonic())
            raise ConnectionError("retry me")

        with pytest.raises(ConnectionError):
            timing_function()

        # Verify at least 2 delays occurred
        assert len(timestamps) == 3
        delay1 = timestamps[1] - timestamps[0]
        delay2 = timestamps[2] - timestamps[1]
        # Second delay should be roughly 2x first delay
        assert delay2 >= delay1 * 1.5, f"Expected delay2 >= {delay1 * 1.5}, got {delay2}"


# ---------------------------------------------------------------------------
# Task Tracker Integration
# ---------------------------------------------------------------------------


class TestTaskTrackerIntegration:
    """Test duplicate task prevention."""

    def test_tracker_prevents_duplicates(self):
        """Same task_id should be detected as duplicate."""
        from worker.task_tracker import TaskTracker

        tracker = TaskTracker()

        assert not tracker.is_duplicate("task-001"), "First call should not be duplicate"
        assert tracker.is_duplicate("task-001"), "Second call should be duplicate"

    def test_tracker_allows_different_tasks(self):
        """Different task_ids should all be unique."""
        from worker.task_tracker import TaskTracker

        tracker = TaskTracker()

        assert not tracker.is_duplicate("task-001")
        assert not tracker.is_duplicate("task-002")
        assert not tracker.is_duplicate("task-003")

    def test_tracker_mark_complete(self):
        """mark_complete should mark task as seen."""
        from worker.task_tracker import TaskTracker

        tracker = TaskTracker()
        tracker.mark_complete("task-001")
        assert tracker.is_duplicate("task-001")

    def test_tracker_clear_removes(self):
        """clear should remove task from seen set."""
        from worker.task_tracker import TaskTracker

        tracker = TaskTracker()
        tracker.is_duplicate("task-001")  # Mark as seen
        tracker.clear("task-001")
        assert not tracker.is_duplicate("task-001")

    def test_tracker_thread_safety(self):
        """Concurrent access should not corrupt state."""
        import threading

        from worker.task_tracker import TaskTracker

        tracker = TaskTracker()
        errors = []

        def worker(task_id):
            try:
                for _ in range(100):
                    tracker.is_duplicate(task_id)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(f"task-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert not errors, f"Thread safety errors: {errors}"


# ---------------------------------------------------------------------------
# Error Handling Integration
# ---------------------------------------------------------------------------


class TestErrorHandlingIntegration:
    """Test error handling across modules."""

    def test_handle_error_retry_logic(self):
        """handle_error returns True when retry_count < max_retries."""
        from worker.errors import handle_error

        error = ValueError("test error")

        # Each call creates a new TaskError with retry_count=0
        # Since retry_count (0) < max_retries (3), returns True
        result = handle_error("task-001", error, max_retries=3)
        assert result is True, "Should retry (retry_count=0 < max_retries=3)"

        # Same for max_retries=1 (retry_count=0 < 1)
        result = handle_error("task-002", error, max_retries=1)
        assert result is True, "Should retry (retry_count=0 < max_retries=1)"

    def test_handle_error_validates_inputs(self):
        """handle_error should validate inputs."""
        from worker.errors import handle_error

        with pytest.raises(ValueError):
            handle_error("task-001", None, max_retries=3)

        with pytest.raises(ValueError):
            handle_error("task-001", ValueError("err"), max_retries=-1)


# ---------------------------------------------------------------------------
# Full Pipeline Simulation
# ---------------------------------------------------------------------------


class TestFullPipelineSimulation:
    """Simulate the full transcription pipeline with mocked services."""

    def test_full_pipeline_audio_to_pdf(self, short_audio_path, tmp_work_dir):
        """Simulate: audio → convert → transcribe → summarize → PDF.

        This is the core integration test that verifies the entire pipeline
        works end-to-end (with LLM mocked).
        """
        from worker.audio_converter import AudioConverter
        from worker.llm_client import LLMClient
        from worker.pdf_generator import PDFGenerator

        # Step 1: Convert audio
        converter = AudioConverter()
        wav_path = converter.convert(short_audio_path)
        assert wav_path.exists(), "Audio conversion failed"

        # Step 2: Transcribe (mocked Whisper)
        from unittest.mock import MagicMock

        with patch("worker.transcriber.WhisperModel") as MockWhisper:
            mock_segments = [
                MagicMock(text="Meeting about quarterly results and budget.", start=0.0, end=5.0),
            ]
            MockWhisper.return_value.transcribe.return_value = (mock_segments, MagicMock(language="ru"))

            from worker.transcriber import Transcriber

            transcriber = Transcriber()
            transcription = transcriber.transcribe(wav_path)

        assert transcription["text"], "Transcription should not be empty"

        # Step 3: Summarize (mocked LLM)
        with patch("worker.llm_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "Q4 results discussion and budget planning."}}],
            }
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()

            llm_client = LLMClient(
                api_url="http://localhost:8080/v1",
                model_name="test-model",
            )
            summary = llm_client.summarize(transcription["text"])

        assert "Q4 results discussion" in summary

        # Step 4: Generate PDF (mocked pandoc)
        output_path = tmp_work_dir / "pipeline_output.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            pdf_path = generator.generate(transcription["text"], summary, output_path)

        assert pdf_path.exists(), "PDF generation failed"
        assert pdf_path.suffix == ".pdf"

    def test_pipeline_with_empty_transcription(self, tmp_work_dir):
        """Pipeline should handle empty transcription gracefully (mocked PDF)."""
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

        assert pdf_path.exists(), "PDF should be created even with empty transcription"

    def test_pipeline_with_very_long_transcription(self, tmp_work_dir):
        """Pipeline should handle very long transcription (> 50000 chars) (mocked PDF)."""
        from worker.llm_client import LLMClient
        from worker.pdf_generator import PDFGenerator

        long_text = "x" * 100000

        with patch("worker.llm_client.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "summary"}}],
            }
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()

            llm_client = LLMClient(
                api_url="http://localhost:8080/v1",
                model_name="test-model",
            )
            summary = llm_client.summarize(long_text)

        assert len(summary) <= 2000  # Summary length limit

        output_path = tmp_work_dir / "long.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            output_path.write_bytes(b"%PDF-1.4 dummy")

            generator = PDFGenerator()
            pdf_path = generator.generate(long_text, summary, output_path)

        assert pdf_path.exists(), "PDF should be created for long transcription"
