"""Tests for ``worker.pipeline.process_transcription``."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worker.pipeline import process_transcription

_PATCH_TARGET_LLM = "worker.pipeline.LLMClient"
_PATCH_TARGET_PDF = "worker.pipeline.PDFGenerator"


def _make_mock_llm(summarize_return: str = "Summary text"):
    """Return a mocked LLMClient instance."""
    mock = MagicMock()
    mock.summarize.return_value = summarize_return
    return mock


def _make_mock_pdf_generator():
    """Return a mocked PDFGenerator instance."""
    mock = MagicMock()
    return mock


class TestProcessTranscription:
    """Tests for process_transcription()."""

    def test_process_transcription_returns_pdf_path(self, tmp_path):
        """Given: valid transcript text
        When: process_transcription called
        Then: returns Path to generated PDF"""
        transcript = "This is a test transcription with meaningful content."
        api_url = "http://localhost:8080/v1"
        model_name = "test-model"
        data_dir = str(tmp_path)

        mock_llm = _make_mock_llm("Test summary")
        mock_pdf = _make_mock_pdf_generator()
        expected_pdf = tmp_path / "summaries" / "test" / "transcription.pdf"
        expected_pdf.parent.mkdir(parents=True)
        expected_pdf.write_bytes(b"%PDF-1.4")
        mock_pdf.generate.return_value = expected_pdf

        with (
            patch(_PATCH_TARGET_LLM, return_value=mock_llm) as mock_llm_cls,
            patch(_PATCH_TARGET_PDF, return_value=mock_pdf) as mock_pdf_cls,
        ):
            result = process_transcription(transcript, api_url, model_name, data_dir)

        assert isinstance(result, Path)
        assert result.exists()
        assert result.name == "transcription.pdf"
        assert "summaries" in str(result)
        mock_llm_cls.assert_called_once_with(api_url, model_name)
        mock_pdf_cls.assert_called_once()

    def test_process_transcription_empty_raises(self, tmp_path):
        """Given: empty transcript text
        When: process_transcription called
        Then: raises ValueError"""
        api_url = "http://localhost:8080/v1"
        model_name = "test-model"
        data_dir = str(tmp_path)

        with patch(_PATCH_TARGET_LLM) as mock_llm_cls:  # noqa: SIM117
            with pytest.raises(ValueError, match="must not be empty"):
                process_transcription("", api_url, model_name, data_dir)

        mock_llm_cls.assert_not_called()

    def test_process_transcription_whitespace_raises(self, tmp_path):
        """Given: whitespace-only transcript text
        When: process_transcription called
        Then: raises ValueError"""
        api_url = "http://localhost:8080/v1"
        model_name = "test-model"
        data_dir = str(tmp_path)

        with patch(_PATCH_TARGET_LLM) as mock_llm_cls:  # noqa: SIM117
            with pytest.raises(ValueError, match="must not be empty"):
                process_transcription("   \n\t  ", api_url, model_name, data_dir)

        mock_llm_cls.assert_not_called()

    def test_process_transcription_creates_summary_dir(self, tmp_path):
        """Given: valid transcript
        When: process_transcription called
        Then: creates data/summaries/<timestamp>/ directory"""
        transcript = "Test transcription"
        api_url = "http://localhost:8080/v1"
        model_name = "test-model"
        data_dir = str(tmp_path / "fresh_data")
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        mock_llm = _make_mock_llm("Summary")
        mock_pdf = _make_mock_pdf_generator()
        output_dir = tmp_path / "summaries" / "20260101_000000"
        output_dir.mkdir(parents=True)
        expected_pdf = output_dir / "transcription.pdf"
        expected_pdf.write_bytes(b"%PDF")
        mock_pdf.generate.return_value = expected_pdf

        with (
            patch(_PATCH_TARGET_LLM, return_value=mock_llm),
            patch(_PATCH_TARGET_PDF, return_value=mock_pdf),
        ):
            process_transcription(transcript, api_url, model_name, data_dir)

        # Verify summaries directory was created
        summaries_dir = tmp_path / "summaries"
        assert summaries_dir.exists()
        assert summaries_dir.is_dir()
        # Verify subdirectory with timestamp pattern was created
        subdirs = [d for d in summaries_dir.iterdir() if d.is_dir()]
        assert len(subdirs) == 1
        # Timestamp dir matches YYYYMMDD_HHMMSS pattern
        dir_name = subdirs[0].name
        assert len(dir_name) == 15  # YYYYMMDD_HHMMSS
        assert dir_name[8] == "_"

    def test_process_transcription_empty_summary_raises(self, tmp_path):
        """Given: LLM returns empty summary
        When: process_transcription called
        Then: raises ValueError"""
        transcript = "Some transcription"
        api_url = "http://localhost:8080/v1"
        model_name = "test-model"
        data_dir = str(tmp_path)

        mock_llm = _make_mock_llm("")
        mock_pdf = _make_mock_pdf_generator()

        with patch(_PATCH_TARGET_LLM, return_value=mock_llm):  # noqa: SIM117
            with pytest.raises(ValueError, match="empty summary"):
                process_transcription(transcript, api_url, model_name, data_dir)

        mock_pdf.assert_not_called()

    def test_process_transcription_uses_correct_api_params(self, tmp_path):
        """Given: specific api_url and model_name
        When: process_transcription called
        Then: LLMClient initialized with those exact values"""
        transcript = "Transcription content"
        api_url = "http://custom-api:9999/v1"
        model_name = "custom-model-v2"
        data_dir = str(tmp_path)

        mock_llm = _make_mock_llm("Summary")
        mock_pdf = _make_mock_pdf_generator()
        output_dir = tmp_path / "summaries" / "20260101_000000"
        output_dir.mkdir(parents=True)
        expected_pdf = output_dir / "transcription.pdf"
        expected_pdf.write_bytes(b"%PDF")
        mock_pdf.generate.return_value = expected_pdf

        with (
            patch(_PATCH_TARGET_LLM, return_value=mock_llm) as mock_llm_cls,
            patch(_PATCH_TARGET_PDF, return_value=mock_pdf),
        ):
            process_transcription(transcript, api_url, model_name, data_dir)

        mock_llm_cls.assert_called_once_with(api_url, model_name)

    def test_process_transcription_logs_stages(self, tmp_path, caplog):
        """Given: valid transcript
        When: process_transcription called
        Then: logs LLM summary and PDF generation stages"""
        transcript = "Test transcription"
        api_url = "http://localhost:8080/v1"
        model_name = "test-model"
        data_dir = str(tmp_path)

        mock_llm = _make_mock_llm("Summary")
        mock_pdf = _make_mock_pdf_generator()
        output_dir = tmp_path / "summaries" / "20260101_000000"
        output_dir.mkdir(parents=True)
        expected_pdf = output_dir / "transcription.pdf"
        expected_pdf.write_bytes(b"%PDF")
        mock_pdf.generate.return_value = expected_pdf

        with (
            patch(_PATCH_TARGET_LLM, return_value=mock_llm),
            patch(_PATCH_TARGET_PDF, return_value=mock_pdf),
            caplog.at_level(logging.INFO),
        ):
            process_transcription(transcript, api_url, model_name, data_dir)

        messages = [r.message for r in caplog.records]
        assert any("LLM summary" in m and "started" in m for m in messages)
        assert any("LLM summary generated" in m for m in messages)
        assert any("PDF generated:" in m for m in messages)

    def test_process_transcription_calls_pdf_generate_with_correct_args(self, tmp_path):
        """Given: valid transcript and summary
        When: process_transcription called
        Then: PDFGenerator.generate called with transcript, summary, and output path"""
        transcript = "Transcription text here"
        summary_text = "Generated summary"
        api_url = "http://localhost:8080/v1"
        model_name = "test-model"
        data_dir = str(tmp_path)

        mock_llm = _make_mock_llm(summary_text)
        mock_pdf = _make_mock_pdf_generator()
        output_dir = tmp_path / "summaries" / "20260101_000000"
        output_dir.mkdir(parents=True)
        expected_pdf = output_dir / "transcription.pdf"
        expected_pdf.write_bytes(b"%PDF")
        mock_pdf.generate.return_value = expected_pdf

        with (
            patch(_PATCH_TARGET_LLM, return_value=mock_llm),
            patch(_PATCH_TARGET_PDF, return_value=mock_pdf),
        ):
            process_transcription(transcript, api_url, model_name, data_dir)

        mock_pdf.generate.assert_called_once()
        call_args = mock_pdf.generate.call_args
        assert call_args[0][0] == transcript
        assert call_args[0][1] == summary_text
        assert call_args[0][2].name == "transcription.pdf"

    def test_process_transcription_summary_truncated_to_max_length(self, tmp_path):
        """Given: LLM returns very long summary
        When: process_transcription called
        Then: summary is truncated to MAX_SUMMARY_LENGTH before PDF generation"""
        long_summary = "x" * 5000
        transcript = "Transcription"
        api_url = "http://localhost:8080/v1"
        model_name = "test-model"
        data_dir = str(tmp_path)

        # Use a real LLMClient so its built-in truncation applies,
        # but mock requests.post to avoid network calls.
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": long_summary}}],
        }
        mock_response.raise_for_status.return_value = None

        output_dir = tmp_path / "summaries" / "20260101_000000"
        output_dir.mkdir(parents=True)
        expected_pdf = output_dir / "transcription.pdf"
        expected_pdf.write_bytes(b"%PDF")

        mock_pdf = _make_mock_pdf_generator()
        mock_pdf.generate.return_value = expected_pdf

        with (
            patch("worker.llm_client.requests.post", return_value=mock_response),
            patch(_PATCH_TARGET_PDF, return_value=mock_pdf),
        ):
            process_transcription(transcript, api_url, model_name, data_dir)

        call_args = mock_pdf.generate.call_args
        # LLMClient truncates to MAX_SUMMARY_LENGTH (2000)
        assert len(call_args[0][1]) == 2000
