"""PDF Uploader for Matrix — sends PDF files as m.file messages."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFUploader:
    """Upload PDF files to a Matrix room as file messages.

    Attributes:
        MAX_FILE_SIZE: Maximum allowed PDF size in bytes (50 MB).
        client: Matrix AsyncClient instance.
    """

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    def __init__(self, client) -> None:
        """Initialize with a Matrix AsyncClient.

        Args:
            client: Matrix AsyncClient instance.
        """
        self.client = client

    def upload(self, room_id: str, pdf_path: Path, task_id: str) -> str:
        """Upload a PDF file to a Matrix room.

        Args:
            room_id: Matrix room identifier (must not be empty).
            pdf_path: Path to the PDF file to upload.
            task_id: Task identifier used in filename and body.

        Returns:
            event_id of the sent message.

        Raises:
            ValueError: If room_id is empty or file exceeds MAX_FILE_SIZE.
            FileNotFoundError: If pdf_path does not exist.
        """
        if not room_id or not room_id.strip():
            raise ValueError("room_id must not be empty")

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        file_size = pdf_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"PDF too large: {file_size} bytes (max {self.MAX_FILE_SIZE})"
            )

        with open(pdf_path, "rb") as f:
            file_data = f.read()

        content_uri = self.client.upload(
            file_data,
            content_type="application/pdf",
            filename=f"{task_id}.pdf",
        )

        event_id = self.client.api.send_message(
            room_id,
            "m.room.message",
            {
                "msgtype": "m.file",
                "body": f"{task_id}.pdf",
                "url": content_uri,
                "info": {
                    "mimetype": "application/pdf",
                    "size": file_size,
                },
            },
        )

        logger.info("Uploaded PDF %s to %s", pdf_path, room_id)
        return event_id
