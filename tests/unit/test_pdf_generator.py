"""Unit tests for worker/pdf_generator.py — HTML → PDF via WeasyPrint."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Restore real module if test_queue.py replaced sys.modules["worker.pdf_generator"]
# with a MagicMock (which lacks the real PDFGenerator class).
if "worker.pdf_generator" in sys.modules:
    mod = sys.modules["worker.pdf_generator"]
    if not hasattr(mod, "PDFGenerator") or not hasattr(mod, "generate_pdf"):
        del sys.modules["worker.pdf_generator"]
        for key in list(sys.modules):
            if key.startswith("worker.pdf_generator"):
                del sys.modules[key]

from worker.pdf_generator import PDFGenerator


class TestGenerate:
    """Tests for PDFGenerator.generate()."""

    @pytest.fixture
    def generator(self):
        return PDFGenerator()

    def test_generate_creates_pdf(self, tmp_path, generator):
        """PDF file is created at output_path."""
        transcription = "Hello world"
        summary = "A short summary"
        output_path = tmp_path / "output.pdf"

        with patch("worker.pdf_generator.HTML") as mock_html:
            mock_html.return_value.write_pdf.return_value = None
            result = generator.generate(transcription, summary, output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.suffix == ".pdf"

    def test_generate_contains_summary(self, generator):
        """PDF HTML content includes summary section."""
        transcription = "Some transcription text"
        summary = "This is the summary content"

        html = generator._create_html(transcription, summary)
        assert "<h2>Саммари</h2>" in html
        assert summary in html

    def test_generate_contains_transcription(self, generator):
        """PDF HTML content includes transcription."""
        transcription = "Transcription text here"
        summary = "Summary"

        html = generator._create_html(transcription, summary)
        assert transcription in html
        assert "<h2>Транскрипция</h2>" in html

    def test_generate_contains_timestamp(self, generator):
        """PDF HTML content includes timestamp."""
        transcription = "Text"
        summary = "Summary"

        html = generator._create_html(transcription, summary)
        assert "Дата:" in html
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", html)

    def test_generate_truncates_long_transcription(self, tmp_path, generator):
        """Transcription longer than MAX_TRANSCRIPTION_LENGTH is truncated."""
        long_text = "x" * 60000
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        assert PDFGenerator.MAX_TRANSCRIPTION_LENGTH == 50000

        with patch("worker.pdf_generator.HTML") as mock_html:
            mock_html.return_value.write_pdf.return_value = None
            generator.generate(long_text, summary, output_path)

        # Verify HTML was written with truncated transcription
        html_content = output_path.read_text(encoding="utf-8")
        assert len(long_text[:50000]) in html_content

    def test_generate_skips_empty_summary(self, generator):
        """Empty or sentinel summary skips the summary section."""
        transcription = "Transcription"

        html_empty = generator._create_html(transcription, "")
        assert "<h2>Саммари</h2>" not in html_empty

        html_sentinel = generator._create_html(transcription, "Нет данных для саммари")
        assert "<h2>Саммари</h2>" not in html_sentinel

    def test_generate_returns_output_path(self, tmp_path, generator):
        """generate() returns the output path."""
        transcription = "Text"
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        with patch("worker.pdf_generator.HTML") as mock_html:
            mock_html.return_value.write_pdf.return_value = None
            result = generator.generate(transcription, summary, output_path)

        assert result == output_path
        assert isinstance(result, Path)

    def test_generate_writes_html(self, tmp_path, generator):
        """HTML file is written during generation."""
        transcription = "Text"
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        with patch("worker.pdf_generator.HTML") as mock_html:
            mock_html.return_value.write_pdf.return_value = None
            generator.generate(transcription, summary, output_path)

        assert output_path.exists()
        html_content = output_path.read_text(encoding="utf-8")
        assert "<html" in html_content
        assert "Транскрипция" in html_content


class TestCreateHtml:
    """Tests for PDFGenerator._create_html()."""

    @pytest.fixture
    def generator(self):
        return PDFGenerator()

    def test_html_has_title(self, generator):
        """HTML starts with transcription title."""
        html = generator._create_html("Text", "Summary")
        assert "<h1>Транскрипция</h1>" in html

    def test_html_has_date_line(self, generator):
        """HTML contains date line with timestamp."""
        html = generator._create_html("Text", "Summary")
        assert "Дата:" in html

    def test_html_with_summary_section(self, generator):
        """HTML includes summary section when summary is provided."""
        html = generator._create_html("Transcription", "My summary text")
        assert "<h2>Саммари</h2>" in html
        assert "My summary text" in html

    def test_html_without_summary(self, generator):
        """HTML omits summary section when summary is empty."""
        html = generator._create_html("Transcription", "")
        assert "<h2>Саммари</h2>" not in html

    def test_html_without_sentinel_summary(self, generator):
        """HTML omits summary section when summary is sentinel value."""
        html = generator._create_html("Transcription", "Нет данных для саммари")
        assert "<h2>Саммари</h2>" not in html

    def test_html_structure(self, generator):
        """HTML has correct structure: title, date, summary (optional), transcription."""
        html = generator._create_html("Transcription content", "Summary content")
        assert "<h1>Транскрипция</h1>" in html
        assert "Дата:" in html
        assert "<h2>Саммари</h2>" in html
        assert "Summary content" in html
        assert "<h2>Транскрипция</h2>" in html
        assert "Transcription content" in html

    def test_html_structure_without_summary(self, generator):
        """HTML structure without summary section."""
        html = generator._create_html("Transcription content", "")
        assert "<h2>Саммари</h2>" not in html
        assert "<h2>Транскрипция</h2>" in html

    def test_html_has_doctype_and_style(self, generator):
        """HTML includes DOCTYPE and CSS styles."""
        html = generator._create_html("Text", "Summary")
        assert "<!DOCTYPE html>" in html
        assert "@page" in html
        assert "font-family:" in html
        assert "font-size: 12pt" in html
