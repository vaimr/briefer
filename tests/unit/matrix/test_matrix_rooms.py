"""Tests for room management methods in MatrixClientWrapper.

T2.1.2 — Add Matrix Room Management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def homeserver():
    return "https://matrix.example.com"


@pytest.fixture
def user():
    return "@briefer:example.com"


@pytest.fixture
def password():
    return "secret_password"


@pytest.fixture
def device_name():
    return "briefer-bot"


@pytest.fixture
def wrapper(homeserver, user, password, device_name):
    from bot.matrix.client import MatrixClientWrapper
    w = MatrixClientWrapper(homeserver, user, password, device_name)
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    w._client = mock_client
    w.is_connected = True
    return w


# ---------------------------------------------------------------------------
# get_room
# ---------------------------------------------------------------------------

class TestGetRoom:
    """Test MatrixClientWrapper.get_room()."""

    def test_get_room_returns_room_object(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_room = MagicMock()
        wrapper.client.rooms = {"!room:example.com": mock_room}

        result = wrapper.get_room("!room:example.com")

        assert result is mock_room

    def test_get_room_missing_returns_none(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        wrapper.client.rooms = {}

        result = wrapper.get_room("!missing:example.com")

        assert result is None

    def test_get_room_raises_when_not_connected(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        w = MatrixClientWrapper(homeserver, user, password, device_name)
        # is_connected is False by default

        with pytest.raises(RuntimeError, match="not connected"):
            w.get_room("!room:example.com")

    def test_get_room_empty_room_id_raises(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(ValueError, match="room_id"):
            wrapper.get_room("")


# ---------------------------------------------------------------------------
# join_room
# ---------------------------------------------------------------------------

class TestJoinRoom:
    """Test MatrixClientWrapper.join_room()."""

    @pytest.mark.asyncio
    async def test_join_room_calls_client_join(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_response = MagicMock()
        wrapper.client.join_room = AsyncMock(return_value=mock_response)

        await wrapper.join_room("!room:example.com")

        wrapper.client.join_room.assert_called_once_with("!room:example.com")

    @pytest.mark.asyncio
    async def test_join_room_with_alias(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_response = MagicMock()
        wrapper.client.join_room = AsyncMock(return_value=mock_response)

        await wrapper.join_room("#briefer:example.com")

        wrapper.client.join_room.assert_called_once_with("#briefer:example.com")

    @pytest.mark.asyncio
    async def test_join_room_raises_when_not_connected(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        w = MatrixClientWrapper(homeserver, user, password, device_name)

        with pytest.raises(RuntimeError, match="not connected"):
            await w.join_room("!room:example.com")

    @pytest.mark.asyncio
    async def test_join_room_empty_raises(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(ValueError, match="alias_or_id"):
            await wrapper.join_room("")


# ---------------------------------------------------------------------------
# list_rooms
# ---------------------------------------------------------------------------

class TestListRooms:
    """Test MatrixClientWrapper.list_rooms()."""

    def test_list_rooms_returns_room_objects(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        room1 = MagicMock()
        room2 = MagicMock()
        wrapper.client.rooms = {"!room1:example.com": room1, "!room2:example.com": room2}

        result = wrapper.list_rooms()

        assert len(result) == 2
        assert room1 in result
        assert room2 in result

    def test_list_rooms_empty_returns_empty_list(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        wrapper.client.rooms = {}

        result = wrapper.list_rooms()

        assert result == []

    def test_list_rooms_raises_when_not_connected(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        w = MatrixClientWrapper(homeserver, user, password, device_name)

        with pytest.raises(RuntimeError, match="not connected"):
            w.list_rooms()


# ---------------------------------------------------------------------------
# send_text
# ---------------------------------------------------------------------------

class TestSendText:
    """Test MatrixClientWrapper.send_text()."""

    @pytest.mark.asyncio
    async def test_send_text_calls_room_send(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        wrapper.client.room_send = AsyncMock()

        await wrapper.send_text("!room:example.com", "Hello world")

        wrapper.client.room_send.assert_called_once_with(
            "!room:example.com",
            "m.room.message",
            {"msgtype": "m.text", "body": "Hello world"},
        )

    @pytest.mark.asyncio
    async def test_send_text_raises_when_not_connected(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        w = MatrixClientWrapper(homeserver, user, password, device_name)

        with pytest.raises(RuntimeError, match="not connected"):
            await w.send_text("!room:example.com", "Hello")

    @pytest.mark.asyncio
    async def test_send_text_empty_room_raises(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(ValueError, match="room_id"):
            await wrapper.send_text("", "Hello")

    @pytest.mark.asyncio
    async def test_send_text_empty_body_raises(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(ValueError, match="body"):
            await wrapper.send_text("!room:example.com", "")


# ---------------------------------------------------------------------------
# send_image
# ---------------------------------------------------------------------------

class TestSendImage:
    """Test MatrixClientWrapper.send_image()."""

    @pytest.mark.asyncio
    async def test_send_image_uploads_and_sends(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_response = MagicMock()
        mock_response.content_uri = "mxc://example.com/img123"
        wrapper.client.upload = AsyncMock(return_value=mock_response)
        wrapper.client.room_send = AsyncMock()

        file_bytes = b"\x89PNG\r\n\x1a\nfake_image_data"
        await wrapper.send_image("!room:example.com", file_bytes, "photo.png")

        wrapper.client.upload.assert_called_once()
        call_args = wrapper.client.upload.call_args
        assert call_args.kwargs["content_type"] == "image/png"

        wrapper.client.room_send.assert_called_once()
        send_args = wrapper.client.room_send.call_args[0]
        send_content = send_args[2]
        assert send_content["msgtype"] == "m.image"
        assert "url" in send_content

    @pytest.mark.asyncio
    async def test_send_image_jpg_mime(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_response = MagicMock()
        mock_response.content_uri = "mxc://example.com/img456"
        wrapper.client.upload = AsyncMock(return_value=mock_response)
        wrapper.client.room_send = AsyncMock()

        file_bytes = b"fake_jpeg_data"
        await wrapper.send_image("!room:example.com", file_bytes, "photo.jpg")

        call_args = wrapper.client.upload.call_args
        assert call_args.kwargs["content_type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_send_image_gif_mime(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_response = MagicMock()
        mock_response.content_uri = "mxc://example.com/img789"
        wrapper.client.upload = AsyncMock(return_value=mock_response)
        wrapper.client.room_send = AsyncMock()

        file_bytes = b"fake_gif_data"
        await wrapper.send_image("!room:example.com", file_bytes, "anim.gif")

        call_args = wrapper.client.upload.call_args
        assert call_args.kwargs["content_type"] == "image/gif"

    @pytest.mark.asyncio
    async def test_send_image_raises_when_not_connected(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        w = MatrixClientWrapper(homeserver, user, password, device_name)

        with pytest.raises(RuntimeError, match="not connected"):
            await w.send_image("!room:example.com", b"data", "photo.png")

    @pytest.mark.asyncio
    async def test_send_image_empty_room_raises(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(ValueError, match="room_id"):
            await wrapper.send_image("", b"data", "photo.png")

    @pytest.mark.asyncio
    async def test_send_image_empty_data_raises(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(ValueError, match="data"):
            await wrapper.send_image("!room:example.com", b"", "photo.png")

    @pytest.mark.asyncio
    async def test_send_image_empty_filename_raises(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(ValueError, match="filename"):
            await wrapper.send_image("!room:example.com", b"data", "")
