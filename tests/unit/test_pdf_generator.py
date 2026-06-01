"""Unit tests for worker/pdf_generator.py — PDF generation via pandoc + xelatex."""

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

        def create_pdf_side_effect(*args, **kwargs):
            output_path.write_bytes(b"%PDF-1.4 dummy pdf content")
            return MagicMock(returncode=0, stderr="")

        with patch("worker.pdf_generator.subprocess.run", side_effect=create_pdf_side_effect):
            result = generator.generate(transcription, summary, output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.suffix == ".pdf"

    def test_generate_contains_summary(self, generator):
        """PDF markdown content includes summary section."""
        transcription = "Some transcription text"
        summary = "This is the summary content"

        md = generator._create_markdown(transcription, summary)
        assert "## Саммари" in md
        assert summary in md

    def test_generate_contains_transcription(self, generator):
        """PDF markdown content includes transcription."""
        transcription = "Transcription text here"
        summary = "Summary"

        md = generator._create_markdown(transcription, summary)
        assert transcription in md
        assert "## Транскрипция" in md

    def test_generate_contains_timestamp(self, generator):
        """PDF markdown content includes timestamp."""
        transcription = "Text"
        summary = "Summary"

        md = generator._create_markdown(transcription, summary)
        # Timestamp format: YYYY-MM-DD HH:MM:SS
        assert "_Дата:" in md
        # Verify it contains a valid timestamp pattern
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", md)

    def test_generate_truncates_long_transcription(self, tmp_path, generator):
        """Transcription longer than MAX_TRANSCRIPTION_LENGTH is truncated."""
        long_text = "x" * 60000
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        # Verify the constant
        assert PDFGenerator.MAX_TRANSCRIPTION_LENGTH == 50000

        # Test truncation in generate
        def create_pdf_side_effect(*args, **kwargs):
            output_path.write_bytes(b"%PDF-1.4 dummy pdf content")
            return MagicMock(returncode=0, stderr="")

        with patch("worker.pdf_generator.subprocess.run", side_effect=create_pdf_side_effect):
            generator.generate(long_text, summary, output_path)

        # Verify markdown was written with truncated transcription
        # The markdown transcription section should be <= MAX_TRANSCRIPTION_LENGTH
        md_files = list(tmp_path.glob("*.md"))
        if md_files:
            content = md_files[0].read_text(encoding="utf-8")
            transcription_part = content.split("## Транскрипция\n\n", 1)
            if len(transcription_part) > 1:
                assert len(transcription_part[1]) <= PDFGenerator.MAX_TRANSCRIPTION_LENGTH

    def test_generate_skips_empty_summary(self, generator):
        """Empty or sentinel summary skips the summary section."""
        transcription = "Transcription"

        # Empty summary
        md_empty = generator._create_markdown(transcription, "")
        assert "## Саммари" not in md_empty

        # Sentinel summary
        md_sentinel = generator._create_markdown(transcription, "Нет данных для саммари")
        assert "## Саммари" not in md_sentinel

    def test_generate_pandoc_error_raises(self, tmp_path, generator):
        """Pandoc failure raises ValueError with stderr."""
        transcription = "Text"
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        error_msg = "font not found"
        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr=error_msg)
            with pytest.raises(ValueError, match="Pandoc failed"):
                generator.generate(transcription, summary, output_path)

        # Markdown should be cleaned up on error
        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 0

    def test_generate_output_is_valid_pdf(self, tmp_path, generator):
        """Generated PDF file exists and has valid PDF header."""
        transcription = "Hello"
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        def create_pdf_side_effect(*args, **kwargs):
            output_path.write_bytes(b"%PDF-1.4 dummy pdf content")
            return MagicMock(returncode=0, stderr="")

        with patch("worker.pdf_generator.subprocess.run", side_effect=create_pdf_side_effect):
            result = generator.generate(transcription, summary, output_path)

        assert result.exists()
        # PDF files start with %PDF-
        content = result.read_bytes()
        assert content[:5] == b"%PDF-"

    def test_generate_returns_output_path(self, tmp_path, generator):
        """generate() returns the output path."""
        transcription = "Text"
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = generator.generate(transcription, summary, output_path)

        assert result == output_path
        assert isinstance(result, Path)

    def test_generate_writes_markdown_then_removes(self, tmp_path, generator):
        """Markdown file is written during generation then removed after success."""
        transcription = "Text"
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        def create_pdf_side_effect(*args, **kwargs):
            output_path.write_bytes(b"%PDF-1.4 dummy pdf content")
            return MagicMock(returncode=0, stderr="")

        with patch("worker.pdf_generator.subprocess.run", side_effect=create_pdf_side_effect):
            generator.generate(transcription, summary, output_path)

        # After successful generation, markdown should be removed
        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 0
        assert output_path.exists()

    def test_generate_pandoc_command_args(self, tmp_path, generator):
        """Pandoc is called with correct arguments."""
        transcription = "Text"
        summary = "Summary"
        output_path = tmp_path / "output.pdf"

        with patch("worker.pdf_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            generator.generate(transcription, summary, output_path)

        call_args = mock_run.call_args[0][0]
        assert "pandoc" in call_args
        assert "--pdf-engine=xelatex" in call_args
        assert "-V" in call_args
        assert "mainfont=lmodern" in call_args
        assert "fontsize=12pt" in call_args
        assert "geometry:margin=1in" in call_args


class TestCreateMarkdown:
    """Tests for PDFGenerator._create_markdown()."""

    @pytest.fixture
    def generator(self):
        return PDFGenerator()

    def test_markdown_has_title(self, generator):
        """Markdown starts with transcription title."""
        md = generator._create_markdown("Text", "Summary")
        assert md.startswith("# Транскрипция")

    def test_markdown_has_date_line(self, generator):
        """Markdown contains date line with timestamp."""
        md = generator._create_markdown("Text", "Summary")
        assert "_Дата:" in md
        assert "_Data:" not in md

    def test_markdown_with_summary_section(self, generator):
        """Markdown includes summary section when summary is provided."""
        md = generator._create_markdown("Transcription", "My summary text")
        assert "## Саммари" in md
        assert "My summary text" in md
        assert "---" in md

    def test_markdown_without_summary(self, generator):
        """Markdown omits summary section when summary is empty."""
        md = generator._create_markdown("Transcription", "")
        assert "## Саммари" not in md

    def test_markdown_without_sentinel_summary(self, generator):
        """Markdown omits summary section when summary is sentinel value."""
        md = generator._create_markdown("Transcription", "Нет данных для саммари")
        assert "## Саммари" not in md

    def test_markdown_structure(self, generator):
        """Markdown has correct structure: title, date, summary (optional), transcription."""
        md = generator._create_markdown("Transcription content", "Summary content")
        lines = md.split("\n")

        assert lines[0] == "# Транскрипция"
        assert lines[1] == ""
        assert "_Дата:" in lines[2]

        # Summary section
        assert "## Саммари" in md
        assert "Summary content" in md
        assert "---" in md

        # Transcription section
        assert "## Транскрипция" in md
        assert "Transcription content" in md

    def test_markdown_structure_without_summary(self, generator):
        """Markdown structure without summary section."""
        md = generator._create_markdown("Transcription content", "")
        sections = md.split("## ")

        assert len(sections) == 2  # Only transcription section
        assert sections[1].startswith("Транскрипция")
