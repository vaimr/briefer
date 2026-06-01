"""Unit tests for bot/pdf_uploader.py — PDFUploader class.

T5.2 — PDF Uploader for Matrix.
"""

from unittest.mock import MagicMock

import pytest

from bot.pdf_uploader import PDFUploader

# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client():
    """Create a mock Matrix AsyncClient."""
    client = MagicMock()
    client.upload.return_value = "mxc://example.com/pdf_content_id"
    client.api.send_message.return_value = "$event_id_001"
    return client


@pytest.fixture
def uploader(mock_client):
    """PDFUploader instance with mock client."""
    return PDFUploader(mock_client)


@pytest.fixture
def pdf_file(tmp_path):
    """Create a minimal PDF-like file for testing."""
    path = tmp_path / "test.pdf"
    path.write_bytes(b"%PDF-1.4 fake pdf content")
    return path


@pytest.fixture
def large_pdf_file(tmp_path):
    """Create a file larger than MAX_FILE_SIZE."""
    path = tmp_path / "huge.pdf"
    path.write_bytes(b"x" * (51 * 1024 * 1024))  # 51 MB
    return path


@pytest.fixture
def exact_max_pdf_file(tmp_path):
    """Create a file exactly at MAX_FILE_SIZE boundary."""
    path = tmp_path / "max.pdf"
    path.write_bytes(b"x" * PDFUploader.MAX_FILE_SIZE)
    return path


# ---------------------------------------------------------------------------
# test_upload_sends_pdf_to_room
# ---------------------------------------------------------------------------

class TestUploadSendsPdfToRoom:
    """Verify PDFUploader.upload sends a file message to the correct room."""

    def test_upload_calls_send_message_with_room_id(self, uploader, pdf_file, mock_client):
        """upload() calls client.api.send_message with the given room_id."""
        uploader.upload("!room:example.com", pdf_file, "task_001")
        mock_client.api.send_message.assert_called_once()
        call_args = mock_client.api.send_message.call_args
        assert call_args[0][0] == "!room:example.com"

    def test_upload_calls_client_upload(self, uploader, pdf_file, mock_client):
        """upload() calls client.upload with file data."""
        uploader.upload("!room:example.com", pdf_file, "task_001")
        mock_client.upload.assert_called_once()

    def test_upload_sends_m_file_msgtype(self, uploader, pdf_file, mock_client):
        """upload() sends message with msgtype='m.file'."""
        uploader.upload("!room:example.com", pdf_file, "task_001")
        call_args = mock_client.api.send_message.call_args
        message_body = call_args[0][2]
        assert message_body["msgtype"] == "m.file"

    def test_upload_sends_correct_filename_in_upload(self, uploader, pdf_file, mock_client):
        """upload() passes filename=f'{task_id}.pdf' to client.upload."""
        uploader.upload("!room:example.com", pdf_file, "my_task")
        call_args = mock_client.upload.call_args
        assert call_args[1]["filename"] == "my_task.pdf"


# ---------------------------------------------------------------------------
# test_upload_returns_event_id
# ---------------------------------------------------------------------------

class TestUploadReturnsEventId:
    """Verify PDFUploader.upload returns the event_id."""

    def test_upload_returns_event_id_string(self, uploader, pdf_file, mock_client):
        """upload() returns the event_id from send_message."""
        result = uploader.upload("!room:example.com", pdf_file, "task_001")
        assert result == "$event_id_001"

    def test_upload_returns_non_empty_string(self, uploader, pdf_file, mock_client):
        """upload() returns a non-empty string."""
        result = uploader.upload("!room:example.com", pdf_file, "task_001")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# test_upload_file_not_found_raises
# ---------------------------------------------------------------------------

class TestUploadFileNotFoundRaises:
    """Verify PDFUploader.upload raises FileNotFoundError for missing files."""

    def test_upload_missing_file_raises_file_not_found(self, uploader, tmp_path):
        """upload() raises FileNotFoundError when pdf_path does not exist."""
        missing_path = tmp_path / "nonexistent.pdf"
        with pytest.raises(FileNotFoundError, match="PDF not found"):
            uploader.upload("!room:example.com", missing_path, "task_001")

    def test_upload_missing_file_does_not_call_client(self, uploader, tmp_path, mock_client):
        """upload() does not call client methods when file is missing."""
        missing_path = tmp_path / "nonexistent.pdf"
        with pytest.raises(FileNotFoundError):
            uploader.upload("!room:example.com", missing_path, "task_001")
        mock_client.upload.assert_not_called()
        mock_client.api.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# test_upload_file_too_large_raises
# ---------------------------------------------------------------------------

class TestUploadFileTooLargeRaises:
    """Verify PDFUploader.upload raises ValueError for oversized files."""

    def test_upload_file_over_max_raises_value_error(self, uploader, large_pdf_file):
        """upload() raises ValueError when file exceeds 50 MB."""
        with pytest.raises(ValueError, match="PDF too large"):
            uploader.upload("!room:example.com", large_pdf_file, "task_001")

    def test_upload_file_over_max_does_not_call_client(self, uploader, large_pdf_file, mock_client):
        """upload() does not call client methods when file is too large."""
        with pytest.raises(ValueError):
            uploader.upload("!room:example.com", large_pdf_file, "task_001")
        mock_client.upload.assert_not_called()
        mock_client.api.send_message.assert_not_called()

    def test_upload_file_at_max_size_accepts(self, uploader, exact_max_pdf_file, mock_client):
        """upload() accepts a file exactly at MAX_FILE_SIZE boundary."""
        uploader.upload("!room:example.com", exact_max_pdf_file, "task_001")
        mock_client.upload.assert_called_once()


# ---------------------------------------------------------------------------
# test_upload_empty_room_raises
# ---------------------------------------------------------------------------

class TestUploadEmptyRoomRaises:
    """Verify PDFUploader.upload raises ValueError for empty room_id."""

    def test_upload_empty_string_room_raises(self, uploader, pdf_file):
        """upload() raises ValueError when room_id is empty string."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            uploader.upload("", pdf_file, "task_001")

    def test_upload_whitespace_room_raises(self, uploader, pdf_file):
        """upload() raises ValueError when room_id is whitespace only."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            uploader.upload("   ", pdf_file, "task_001")

    def test_upload_empty_room_does_not_call_client(self, uploader, pdf_file, mock_client):
        """upload() does not call client methods when room_id is empty."""
        with pytest.raises(ValueError):
            uploader.upload("", pdf_file, "task_001")
        mock_client.upload.assert_not_called()
        mock_client.api.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# test_upload_correct_content_type
# ---------------------------------------------------------------------------

class TestUploadContentType:
    """Verify PDFUploader.upload uses correct content_type and message info."""

    def test_upload_uses_application_pdf_content_type(self, uploader, pdf_file, mock_client):
        """upload() passes content_type='application/pdf' to client.upload."""
        uploader.upload("!room:example.com", pdf_file, "task_001")
        call_args = mock_client.upload.call_args
        assert call_args[1]["content_type"] == "application/pdf"

    def test_upload_message_info_contains_mimetype(self, uploader, pdf_file, mock_client):
        """upload() includes mimetype='application/pdf' in message info."""
        uploader.upload("!room:example.com", pdf_file, "task_001")
        call_args = mock_client.api.send_message.call_args
        message_body = call_args[0][2]
        assert message_body["info"]["mimetype"] == "application/pdf"

    def test_upload_message_info_contains_size(self, uploader, pdf_file, mock_client):
        """upload() includes file size in message info."""
        uploader.upload("!room:example.com", pdf_file, "task_001")
        call_args = mock_client.api.send_message.call_args
        message_body = call_args[0][2]
        assert message_body["info"]["size"] == pdf_file.stat().st_size

    def test_upload_message_contains_url(self, uploader, pdf_file, mock_client):
        """upload() includes content_uri as url in message body."""
        uploader.upload("!room:example.com", pdf_file, "task_001")
        call_args = mock_client.api.send_message.call_args
        message_body = call_args[0][2]
        assert message_body["url"] == "mxc://example.com/pdf_content_id"

    def test_upload_message_contains_body(self, uploader, pdf_file, mock_client):
        """upload() includes task_id.pdf as body in message."""
        uploader.upload("!room:example.com", pdf_file, "summary_v2")
        call_args = mock_client.api.send_message.call_args
        message_body = call_args[0][2]
        assert message_body["body"] == "summary_v2.pdf"


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------

class TestConstants:
    """Validate class constants match spec."""

    def test_max_file_size_is_50mb(self):
        assert PDFUploader.MAX_FILE_SIZE == 50 * 1024 * 1024

    def test_max_file_size_value(self):
        assert PDFUploader.MAX_FILE_SIZE == 52428800
