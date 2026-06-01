"""Unit tests for bot/result_consumer.py — deliver_result function.

T5.3 — Bot Error Handling for Result Delivery.
"""

from unittest.mock import MagicMock, patch

import pytest

from bot.result_consumer import deliver_result

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
def pdf_file(tmp_path):
    """Create a minimal PDF-like file for testing."""
    path = tmp_path / "test.pdf"
    path.write_bytes(b"%PDF-1.4 fake pdf content")
    return path


# ---------------------------------------------------------------------------
# test_deliver_result_success
# ---------------------------------------------------------------------------


class TestDeliverResultSuccess:
    """Verify successful delivery returns True and logs correctly."""

    def test_deliver_result_returns_true_on_success(
        self, mock_client, pdf_file
    ):
        """deliver_result() returns True when upload succeeds."""
        result = deliver_result(
            mock_client, "!room:example.com", str(pdf_file), "task_001"
        )
        assert result is True

    def test_deliver_result_calls_pdf_uploader_once(self, mock_client, pdf_file):
        """deliver_result() creates PDFUploader and calls upload once on success."""
        with patch("bot.result_consumer.PDFUploader") as mock_uploader_cls:
            mock_uploader = MagicMock()
            mock_uploader_cls.return_value = mock_uploader
            deliver_result(
                mock_client, "!room:example.com", str(pdf_file), "task_001"
            )
            mock_uploader_cls.assert_called_once_with(mock_client)
            mock_uploader.upload.assert_called_once_with(
                "!room:example.com", pdf_file, "task_001"
            )


# ---------------------------------------------------------------------------
# test_deliver_result_retries_on_error
# ---------------------------------------------------------------------------


class TestDeliverResultRetriesOnError:
    """Verify deliver_result retries on transient errors and succeeds."""

    def test_deliver_result_retries_on_error(
        self, mock_client, pdf_file
    ):
        """deliver_result() retries on failure and returns True on third attempt."""
        with patch("bot.result_consumer.PDFUploader") as mock_uploader_cls:
            mock_uploader = MagicMock()
            mock_uploader_cls.return_value = mock_uploader

            # Fail first two attempts, succeed on third
            mock_uploader.upload.side_effect = [
                ConnectionError("connection refused"),
                ConnectionError("connection refused"),
                "$event_id_003",
            ]

            result = deliver_result(
                mock_client, "!room:example.com", str(pdf_file), "task_retry"
            )

            assert result is True
            assert mock_uploader.upload.call_count == 3


# ---------------------------------------------------------------------------
# test_deliver_result_max_retries_sends_error
# ---------------------------------------------------------------------------


class TestDeliverResultMaxRetriesExhausted:
    """Verify deliver_result returns False after all retries fail."""

    def test_deliver_result_max_retries_sends_error(
        self, mock_client, pdf_file
    ):
        """deliver_result() returns False after 3 failed attempts."""
        with patch("bot.result_consumer.PDFUploader") as mock_uploader_cls:
            mock_uploader = MagicMock()
            mock_uploader_cls.return_value = mock_uploader

            mock_uploader.upload.side_effect = ConnectionError("connection refused")

            result = deliver_result(
                mock_client, "!room:example.com", str(pdf_file), "task_fail"
            )

            assert result is False
            assert mock_uploader.upload.call_count == 3


# ---------------------------------------------------------------------------
# test_deliver_result_nonexistent_pdf_raises
# ---------------------------------------------------------------------------


class TestDeliverResultNonexistentPdfRaises:
    """Verify deliver_result raises ValueError for missing PDF files."""

    def test_deliver_result_nonexistent_pdf_raises(self, mock_client, tmp_path):
        """deliver_result() raises ValueError when PDF file does not exist."""
        missing_path = str(tmp_path / "nonexistent.pdf")
        with pytest.raises(ValueError, match="PDF not found"):
            deliver_result(
                mock_client, "!room:example.com", missing_path, "task_missing"
            )

    def test_deliver_result_nonexistent_pdf_does_not_create_uploader(
        self, mock_client, tmp_path
    ):
        """deliver_result() does not create PDFUploader when PDF is missing."""
        missing_path = str(tmp_path / "nonexistent.pdf")
        with patch("bot.result_consumer.PDFUploader") as mock_uploader_cls:
            with pytest.raises(ValueError):
                deliver_result(
                    mock_client, "!room:example.com", missing_path, "task_missing"
                )
            mock_uploader_cls.assert_not_called()


# ---------------------------------------------------------------------------
# test_deliver_result_empty_room_raises
# ---------------------------------------------------------------------------


class TestDeliverResultEmptyRoomRaises:
    """Verify deliver_result raises ValueError for empty room_id values."""

    def test_deliver_result_empty_room_raises(self, mock_client, pdf_file):
        """deliver_result() raises ValueError when room_id is empty string."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            deliver_result(mock_client, "", str(pdf_file), "task_001")

    def test_deliver_result_whitespace_room_raises(self, mock_client, pdf_file):
        """deliver_result() raises ValueError when room_id is whitespace only."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            deliver_result(mock_client, "   ", str(pdf_file), "task_001")

    def test_deliver_result_empty_room_does_not_create_uploader(
        self, mock_client, pdf_file
    ):
        """deliver_result() does not create PDFUploader when room_id is empty."""
        with patch("bot.result_consumer.PDFUploader") as mock_uploader_cls:
            with pytest.raises(ValueError):
                deliver_result(mock_client, "", str(pdf_file), "task_001")
            mock_uploader_cls.assert_not_called()


# ---------------------------------------------------------------------------
# test_deliver_result_exponential_backoff
# ---------------------------------------------------------------------------


class TestDeliverResultExponentialBackoff:
    """Verify deliver_result uses exponential backoff delays: 1s, 2s, 4s."""

    def test_deliver_result_exponential_backoff_delays(
        self, mock_client, pdf_file
    ):
        """deliver_result() sleeps 1s, 2s, 4s between retries (base_delay=1, factor=2)."""
        with patch("bot.result_consumer.PDFUploader") as mock_uploader_cls, \
             patch("bot.result_consumer.time.sleep") as mock_sleep:

            mock_uploader = MagicMock()
            mock_uploader_cls.return_value = mock_uploader
            mock_uploader.upload.side_effect = ConnectionError("transient error")

            deliver_result(
                mock_client, "!room:example.com", str(pdf_file), "task_backoff"
            )

            # Verify sleep was called exactly twice (between 3 attempts)
            assert mock_sleep.call_count == 2

            # First retry: base_delay * 2^0 = 1s
            # Second retry: base_delay * 2^1 = 2s
            expected_delays = [1, 2]
            actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert actual_delays == expected_delays

    def test_deliver_result_no_sleep_on_success(self, mock_client, pdf_file):
        """deliver_result() does not call sleep when upload succeeds immediately."""
        with patch("bot.result_consumer.PDFUploader") as mock_uploader_cls, \
             patch("bot.result_consumer.time.sleep") as mock_sleep:

            mock_uploader = MagicMock()
            mock_uploader_cls.return_value = mock_uploader
            mock_uploader.upload.return_value = "$event_id_ok"

            deliver_result(
                mock_client, "!room:example.com", str(pdf_file), "task_ok"
            )

            mock_sleep.assert_not_called()
