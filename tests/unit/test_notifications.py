"""Tests for bot.notifications.send_status."""

from unittest.mock import MagicMock, patch

import pytest

from bot.notifications import MAX_MESSAGE_LENGTH, STATUS_EMOJIS, send_status


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    """Return a fresh MagicMock acting as a Matrix client."""
    client = MagicMock()
    client.room_send.return_value = None
    return client


@pytest.fixture
def valid_room_id():
    return "!abc123:example.com"


@pytest.fixture
def long_message():
    """A message exceeding MAX_MESSAGE_LENGTH."""
    return "x" * (MAX_MESSAGE_LENGTH + 100)


# ---------------------------------------------------------------------------
# Status emoji mapping tests
# ---------------------------------------------------------------------------


class TestSendStatusProcessing:
    """Verify processing status sends the correct emoji and format."""

    def test_emoji_is_sandglass(self, mock_client, valid_room_id):
        """Processing status uses ⏳ emoji."""
        send_status(mock_client, valid_room_id, "processing", "Working…")
        call_args = mock_client.room_send.call_args
        body = call_args[0][2]["body"]
        assert body.startswith("\u23f3")

    def test_room_send_called(self, mock_client, valid_room_id):
        """room_send is invoked exactly once."""
        send_status(mock_client, valid_room_id, "processing", "Working…")
        mock_client.room_send.assert_called_once()

    def test_message_type_is_notice(self, mock_client, valid_room_id):
        """Message is sent as m.notice."""
        send_status(mock_client, valid_room_id, "processing", "Working…")
        call_args = mock_client.room_send.call_args
        content = call_args[0][2]
        assert content["msgtype"] == "m.notice"

    def test_room_id_passed_correctly(self, mock_client, valid_room_id):
        """The correct room_id is passed to room_send."""
        send_status(mock_client, valid_room_id, "processing", "Working…")
        call_args = mock_client.room_send.call_args
        assert call_args[0][0] == valid_room_id


class TestSendStatusDone:
    """Verify done status sends the correct emoji and format."""

    def test_emoji_is_checkmark(self, mock_client, valid_room_id):
        """Done status uses ✅ emoji."""
        send_status(mock_client, valid_room_id, "done", "Done!")
        call_args = mock_client.room_send.call_args
        body = call_args[0][2]["body"]
        assert body.startswith("\u2705")

    def test_room_send_called(self, mock_client, valid_room_id):
        """room_send is invoked for done status."""
        send_status(mock_client, valid_room_id, "done", "Done!")
        mock_client.room_send.assert_called_once()


class TestSendStatusError:
    """Verify error status sends the correct emoji and format."""

    def test_emoji_is_cross(self, mock_client, valid_room_id):
        """Error status uses ❌ emoji."""
        send_status(mock_client, valid_room_id, "error", "Failed!")
        call_args = mock_client.room_send.call_args
        body = call_args[0][2]["body"]
        assert body.startswith("\u274c")

    def test_room_send_called(self, mock_client, valid_room_id):
        """room_send is invoked for error status."""
        send_status(mock_client, valid_room_id, "error", "Failed!")
        mock_client.room_send.assert_called_once()


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestSendStatusInvalidStatusRaises:
    """Verify ValueError is raised for unknown status values."""

    def test_unknown_status_raises(self, mock_client, valid_room_id):
        """ValueError is raised when status is not in STATUS_EMOJIS."""
        with pytest.raises(ValueError, match="Unknown status"):
            send_status(mock_client, valid_room_id, "unknown", "msg")

    def test_numeric_status_raises(self, mock_client, valid_room_id):
        """Numeric string status is rejected."""
        with pytest.raises(ValueError, match="Unknown status"):
            send_status(mock_client, valid_room_id, "42", "msg")

    def test_empty_status_raises(self, mock_client, valid_room_id):
        """Empty string status is rejected."""
        with pytest.raises(ValueError, match="Unknown status"):
            send_status(mock_client, valid_room_id, "", "msg")


class TestSendStatusEmptyRoomRaises:
    """Verify ValueError is raised for empty room_id values."""

    def test_empty_string_room_id_raises(self, mock_client):
        """ValueError is raised when room_id is empty string."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            send_status(mock_client, "", "processing", "msg")

    def test_whitespace_only_room_id_raises(self, mock_client):
        """ValueError is raised when room_id contains only whitespace."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            send_status(mock_client, "   ", "processing", "msg")

    def test_none_room_id_raises(self, mock_client):
        """ValueError is raised when room_id is None."""
        with pytest.raises(ValueError, match="room_id must not be empty"):
            send_status(mock_client, None, "processing", "msg")


# ---------------------------------------------------------------------------
# Message truncation tests
# ---------------------------------------------------------------------------


class TestSendStatusTruncatesLongMessage:
    """Verify messages longer than MAX_MESSAGE_LENGTH are truncated."""

    def test_message_is_truncated(self, mock_client, valid_room_id, long_message):
        """Message exceeding MAX_MESSAGE_LENGTH is truncated."""
        send_status(mock_client, valid_room_id, "processing", long_message)
        call_args = mock_client.room_send.call_args
        body = call_args[0][2]["body"]
        # body = f"{emoji} {truncated}" = 2 + MAX_MESSAGE_LENGTH
        assert len(body) == 2 + MAX_MESSAGE_LENGTH

    def test_truncated_message_length(self, mock_client, valid_room_id, long_message):
        """Truncated message body length equals 2 (emoji + space) + MAX_MESSAGE_LENGTH."""
        send_status(mock_client, valid_room_id, "processing", long_message)
        call_args = mock_client.room_send.call_args
        body = call_args[0][2]["body"]
        assert len(body) <= 2 + MAX_MESSAGE_LENGTH

    def test_short_message_not_truncated(self, mock_client, valid_room_id):
        """Short message is sent unchanged (aside from emoji prefix)."""
        short = "Hello"
        send_status(mock_client, valid_room_id, "processing", short)
        call_args = mock_client.room_send.call_args
        body = call_args[0][2]["body"]
        assert body == f"\u23f3 {short}"

    def test_exactly_max_length_not_truncated(self, mock_client, valid_room_id):
        """Message exactly MAX_MESSAGE_LENGTH is not truncated."""
        exact = "x" * MAX_MESSAGE_LENGTH
        send_status(mock_client, valid_room_id, "processing", exact)
        call_args = mock_client.room_send.call_args
        body = call_args[0][2]["body"]
        assert len(body) == 2 + MAX_MESSAGE_LENGTH


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestSendStatusErrorHandling:
    """Verify errors are caught and logged, not raised."""

    def test_room_send_error_does_not_raise(self, valid_room_id):
        """RoomSendError from Matrix is caught and logged, not re-raised."""
        from nio.responses import RoomSendError

        mock_cli = MagicMock()
        mock_cli.room_send.return_value = RoomSendError(
            "server error", status_code="500", room_id=valid_room_id
        )
        # Should NOT raise
        send_status(mock_cli, valid_room_id, "processing", "msg")
        mock_cli.room_send.assert_called_once()

    def test_room_send_error_is_logged(self, valid_room_id, caplog):
        """RoomSendError is logged at ERROR level."""
        from nio.responses import RoomSendError

        mock_cli = MagicMock()
        mock_cli.room_send.return_value = RoomSendError(
            "server error", status_code="500", room_id=valid_room_id
        )

        with caplog.at_level("ERROR"):
            send_status(mock_cli, valid_room_id, "processing", "msg")

        assert "Failed to send status notification" in caplog.text

    def test_generic_exception_does_not_raise(self, valid_room_id):
        """Any unexpected exception is caught and logged, not re-raised."""
        mock_cli = MagicMock()
        mock_cli.room_send.side_effect = RuntimeError("boom")
        # Should NOT raise
        send_status(mock_cli, valid_room_id, "processing", "msg")

    def test_generic_exception_is_logged(self, valid_room_id, caplog):
        """Unexpected exceptions are logged at ERROR level."""
        mock_cli = MagicMock()
        mock_cli.room_send.side_effect = RuntimeError("boom")

        with caplog.at_level("ERROR"):
            send_status(mock_cli, valid_room_id, "processing", "msg")

        assert "Unexpected error sending status" in caplog.text


# ---------------------------------------------------------------------------
# Logging tests
# ---------------------------------------------------------------------------


class TestSendStatusLogging:
    """Verify successful status sends are logged."""

    def test_success_logs_status(self, mock_client, valid_room_id, caplog):
        """Successful send is logged with status field."""
        with caplog.at_level("INFO"):
            send_status(mock_client, valid_room_id, "done", "All good")

        assert "Status notification sent" in caplog.text
        assert "done" in caplog.text

    def test_success_logs_room_id(self, mock_client, valid_room_id, caplog):
        """Successful send is logged with room_id."""
        with caplog.at_level("INFO"):
            send_status(mock_client, valid_room_id, "processing", "Working…")

        assert valid_room_id in caplog.text
