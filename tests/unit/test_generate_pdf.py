"""Tests for generate_pdf convenience function in worker/pdf_generator.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worker.pdf_generator import generate_pdf


class TestGeneratePdf:
    """Tests for the generate_pdf() convenience wrapper."""

    def test_generate_pdf_calls_pdf_generator(self, tmp_path):
        """generate_pdf() delegates to PDFGenerator.generate()."""
        transcription = "# Test\n\nSummary"
        base_name = "test_output"

        def mock_generate(transcription, summary, output_path):
            output_path.write_bytes(b"%PDF-1.4 dummy")
            return output_path

        with patch("worker.pdf_generator.PDFGenerator") as MockGen:
            MockGen.return_value.generate = mock_generate
            result = generate_pdf(transcription, base_name, output_dir=str(tmp_path))

        assert result.suffix == ".pdf"
        assert result.exists()

    def test_generate_pdf_creates_pdf_extension(self, tmp_path):
        """generate_pdf() ensures output has .pdf extension."""
        def mock_generate(transcription, summary, output_path):
            output_path.write_bytes(b"%PDF-1.4 dummy")
            return output_path

        with patch("worker.pdf_generator.PDFGenerator") as MockGen:
            MockGen.return_value.generate = mock_generate
            result = generate_pdf(transcription="text", base_name="test", output_dir=str(tmp_path))

        assert result.suffix == ".pdf"

    def test_generate_pdf_returns_path(self, tmp_path):
        """generate_pdf() returns a Path object."""
        with patch("worker.pdf_generator.PDFGenerator") as MockGen:
            MockGen.return_value.generate = MagicMock(return_value=tmp_path / "out.pdf")
            result = generate_pdf(transcription="text", base_name="test", output_dir=str(tmp_path))

        assert isinstance(result, Path)

    def test_generate_pdf_passes_transcription(self, tmp_path):
        """generate_pdf() passes transcription text to PDFGenerator."""
        transcription = "Hello world transcription"
        captured_kwargs = {}

        def mock_generate(transcription, summary, output_path):
            captured_kwargs["transcription"] = transcription
            output_path.write_bytes(b"%PDF-1.4 dummy")
            return output_path

        with patch("worker.pdf_generator.PDFGenerator") as MockGen:
            MockGen.return_value.generate = mock_generate
            generate_pdf(transcription, "test", output_dir=str(tmp_path))

        assert captured_kwargs["transcription"] == transcription

    def test_generate_pdf_passes_empty_summary(self, tmp_path):
        """generate_pdf() passes empty summary (wrapper handles it)."""
        captured_kwargs = {}

        def mock_generate(transcription, summary, output_path):
            captured_kwargs["summary"] = summary
            output_path.write_bytes(b"%PDF-1.4 dummy")
            return output_path

        with patch("worker.pdf_generator.PDFGenerator") as MockGen:
            MockGen.return_value.generate = mock_generate
            generate_pdf(transcription="text", base_name="test", output_dir=str(tmp_path))

        assert captured_kwargs["summary"] == ""

    def test_generate_pdf_output_filename(self, tmp_path):
        """generate_pdf() uses base_name for output filename."""
        transcription = "Text"
        base_name = "meeting_summary"

        def mock_generate(transcription, summary, output_path):
            assert output_path.name == f"{base_name}.pdf"
            output_path.write_bytes(b"%PDF-1.4 dummy")
            return output_path

        with patch("worker.pdf_generator.PDFGenerator") as MockGen:
            MockGen.return_value.generate = mock_generate
            generate_pdf(transcription, base_name, output_dir=str(tmp_path))
