"""HTML → PDF generation via WeasyPrint (no system dependencies)."""

import logging
from datetime import datetime
from pathlib import Path

from weasyprint import HTML

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Generate PDF from Markdown text via WeasyPrint."""

    MAX_TRANSCRIPTION_LENGTH = 50000

    def generate(
        self,
        transcription: str,
        summary: str,
        output_path: Path,
    ) -> Path:
        if len(transcription) > self.MAX_TRANSCRIPTION_LENGTH:
            logger.warning(
                "Transcription truncated from %d to %d characters",
                len(transcription),
                self.MAX_TRANSCRIPTION_LENGTH,
            )
            transcription = transcription[: self.MAX_TRANSCRIPTION_LENGTH]

        html = self._create_html(transcription, summary)
        output_path.write_text(html, encoding="utf-8")
        logger.info("Wrote HTML to %s", output_path)

        HTML(string=html).write_pdf(str(output_path))
        logger.info("Generated PDF at %s", output_path)
        return output_path

    def _create_html(self, transcription: str, summary: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        body = (
            f"<h1>Транскрипция</h1>\n"
            f"<p><i>Дата: {timestamp}</i></p>\n"
        )

        if summary and summary != "Нет данных для саммари":
            body += f"<h2>Саммари</h2>\n<p>{summary}</p>\n"
            body += "<hr>\n"

        body += f"<h2>Транскрипция</h2>\n"
        body += transcription.replace("\n", "<br>")

        return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 1in;
  }}
  body {{
    font-family: DejaVu Sans, sans-serif;
    font-size: 12pt;
    line-height: 1.5;
  }}
  h1 {{ font-size: 18pt; }}
  h2 {{ font-size: 14pt; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def generate_pdf(
    transcription: str,
    base_name: str,
    output_dir: str = "/data",
) -> Path:
    gen = PDFGenerator()
    output_path = Path(output_dir) / f"{base_name}.pdf"
    return gen.generate(transcription, "", output_path)
