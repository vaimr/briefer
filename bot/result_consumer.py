"""Result consumer — delivers PDF transcription results to Matrix rooms."""

import logging
import time
from pathlib import Path

from bot.pdf_uploader import PDFUploader

logger = logging.getLogger(__name__)


def deliver_result(client, room_id: str, pdf_path: str, task_id: str) -> bool:
    """Upload a PDF summary to a Matrix room with retry and exponential backoff.

    Args:
        client: Matrix AsyncClient instance.
        room_id: Matrix room identifier (must not be empty).
        pdf_path: Path to the PDF file to deliver.
        task_id: Task identifier used in filename and body.

    Returns:
        True if the PDF was delivered successfully, False after all retries exhausted.

    Raises:
        ValueError: If room_id is empty or pdf_path does not exist.
    """
    if not room_id or not room_id.strip():
        raise ValueError("room_id must not be empty")

    path = Path(pdf_path)
    if not path.exists():
        raise ValueError(f"PDF not found: {pdf_path}")

    uploader = PDFUploader(client)

    max_retries = 3
    base_delay = 1  # seconds

    for attempt in range(max_retries):
        try:
            uploader.upload(room_id, path, task_id)
            logger.info("Delivered result to %s", room_id)
            return True
        except Exception:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Upload attempt %d/%d failed for %s in %s, retrying in %.1fs",
                    attempt + 1,
                    max_retries,
                    task_id,
                    room_id,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "Upload failed after %d attempts for %s in %s",
                    max_retries,
                    task_id,
                    room_id,
                )

    return False
