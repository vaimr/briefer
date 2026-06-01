"""PDF generation from Markdown via pandoc + xelatex."""

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Generate PDF from transcription and summary via pandoc."""

    MAX_TRANSCRIPTION_LENGTH = 50000

    def generate(
        self,
        transcription: str,
        summary: str,
        output_path: Path,
    ) -> Path:
        """Generate a PDF file from transcription and summary.

        Args:
            transcription: Raw transcription text.
            summary: Summary text (may be empty or sentinel value).
            output_path: Path for the output PDF file.

        Returns:
            Path to the generated PDF file.

        Raises:
            ValueError: If pandoc fails to produce the PDF.
        """
        # Truncate transcription if too long
        if len(transcription) > self.MAX_TRANSCRIPTION_LENGTH:
            logger.warning(
                "Transcription truncated from %d to %d characters",
                len(transcription),
                self.MAX_TRANSCRIPTION_LENGTH,
            )
            transcription = transcription[: self.MAX_TRANSCRIPTION_LENGTH]

        # Create markdown content
        markdown = self._create_markdown(transcription, summary)

        # Write markdown to temporary file
        markdown_path = output_path.with_suffix(".md")
        markdown_path.write_text(markdown, encoding="utf-8")
        logger.info("Wrote markdown to %s", markdown_path)

        # Run pandoc: Markdown → PDF via xelatex
        cmd = [
            "pandoc",
            str(markdown_path),
            "-o",
            str(output_path),
            "--pdf-engine=xelatex",
            "-V",
            "mainfont=lmodern",
            "-V",
            "fontsize=12pt",
            "-V",
            "geometry:margin=1in",
        ]

        logger.info("Running pandoc: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            # Clean up markdown on failure
            if markdown_path.exists():
                markdown_path.unlink(missing_ok=True)
            raise ValueError(f"Pandoc failed: {stderr}")

        # Clean up markdown file after successful PDF generation
        if markdown_path.exists():
            markdown_path.unlink(missing_ok=True)
            logger.info("Removed temporary markdown file %s", markdown_path)

        logger.info("Generated PDF at %s", output_path)
        return output_path

    def _create_markdown(self, transcription: str, summary: str) -> str:
        """Create formatted markdown content.

        Args:
            transcription: Transcription text.
            summary: Summary text.

        Returns:
            Formatted markdown string.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        md = "# Транскрипция\n\n"
        md += f"_Дата: {timestamp}_\n\n"

        # Add summary section only if present and not sentinel
        if summary and summary != "Нет данных для саммари":
            md += "## Саммари\n\n"
            md += f"{summary}\n\n"
            md += "---\n\n"

        md += "## Транскрипция\n\n"
        md += transcription

        return md


def generate_pdf(
    transcription: str,
    base_name: str,
    output_dir: str = "/data",
) -> Path:
    """Convenience wrapper around PDFGenerator.

    Given: transcription text and base name
    When: generate_pdf() is called
    Then: a PDF is generated at {output_dir}/{base_name}.pdf
    And: the Path to the PDF is returned

    Args:
        transcription: Transcription / markdown text.
        base_name: Base name for the output PDF file.
        output_dir: Directory for the output PDF.

    Returns:
        Path to the generated PDF file.
    """
    gen = PDFGenerator()
    output_path = Path(output_dir) / f"{base_name}.pdf"
    return gen.generate(transcription, "", output_path)
