"""Tests for bot/matrix/client.py — MatrixClientWrapper.

T2.1.1 — Create Matrix Client Wrapper Base Class
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    """Test MatrixClientWrapper.__init__."""

    def test_init_stores_homeserver(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        assert wrapper.homeserver == homeserver

    def test_init_stores_user(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        assert wrapper.user == user

    def test_init_stores_password(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        assert wrapper.password == password

    def test_init_stores_device_name(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        assert wrapper.device_name == device_name

    def test_init_client_is_none(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        assert wrapper.client is None

    def test_init_is_connected_false(self, homeserver, user, password, device_name):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        assert wrapper.is_connected is False

    def test_init_empty_device_name_defaults(self, homeserver, user, password):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, "",
        )
        assert wrapper.device_name == "briefer-bot"

    def test_init_empty_password_allowed(self, homeserver, user, device_name):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, "", device_name,
        )
        assert wrapper.password == ""


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

class TestConnect:
    """Test MatrixClientWrapper.connect()."""

    @pytest.mark.asyncio
    async def test_connect_creates_client(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        with patch(
            "bot.matrix.client.AsyncClient",
            return_value=MagicMock(),
        ) as mock_client_cls:
            await wrapper.connect()

        mock_client_cls.assert_called_once_with(
            homeserver, user,
        )
        assert wrapper.client is not None

    @pytest.mark.asyncio
    async def test_connect_sets_is_connected(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        with patch("bot.matrix.client.AsyncClient", return_value=MagicMock()):
            await wrapper.connect()

        assert wrapper.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_already_connected_raises(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        wrapper._client = MagicMock()
        wrapper.is_connected = True

        with pytest.raises(RuntimeError, match="already connected"):
            await wrapper.connect()

    @pytest.mark.asyncio
    async def test_connect_calls_set_push_encrypted_to_device_false(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.set_push_encrypted_to_device = AsyncMock()

        with patch(
            "bot.matrix.client.AsyncClient",
            return_value=mock_client,
        ):
            await wrapper.connect()

        mock_client.set_push_encrypted_to_device.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

class TestDisconnect:
    """Test MatrixClientWrapper.disconnect()."""

    @pytest.mark.asyncio
    async def test_disconnect_calls_client_close(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        await wrapper.disconnect()

        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_sets_is_connected_false(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        await wrapper.disconnect()

        assert wrapper.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_without_client_is_noop(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        # No client, no connection — should not raise
        await wrapper.disconnect()
        assert wrapper.is_connected is False


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

class TestLogin:
    """Test MatrixClientWrapper.login()."""

    @pytest.mark.asyncio
    async def test_login_calls_client_login_with_password(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.login = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        await wrapper.login(password)

        mock_client.login.assert_called_once_with(
            password=password, device_name=device_name,
        )

    @pytest.mark.asyncio
    async def test_login_raises_when_not_connected(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        # is_connected is False by default

        with pytest.raises(RuntimeError, match="not connected"):
            await wrapper.login(password)

    @pytest.mark.asyncio
    async def test_login_propagates_exception(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.login = AsyncMock(side_effect=Exception("auth failed"))
        wrapper._client = mock_client
        wrapper.is_connected = True

        with pytest.raises(Exception, match="auth failed"):
            await wrapper.login(password)


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

class TestSendMessage:
    """Test MatrixClientWrapper.send_message()."""

    @pytest.mark.asyncio
    async def test_send_message_calls_room_send(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.room_send = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        await wrapper.send_message(
            room_id="!room:example.com",
            body="Hello world",
        )

        mock_client.room_send.assert_called_once_with(
            "!room:example.com",
            "m.room.message",
            {"msgtype": "m.text", "body": "Hello world"},
        )

    @pytest.mark.asyncio
    async def test_send_message_raises_when_not_connected(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )

        with pytest.raises(RuntimeError, match="not connected"):
            await wrapper.send_message(
                room_id="!room:example.com",
                body="Hello",
            )

    @pytest.mark.asyncio
    async def test_send_message_empty_room_raises(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.room_send = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        with pytest.raises(ValueError, match="room_id"):
            await wrapper.send_message(
                room_id="",
                body="Hello",
            )

    @pytest.mark.asyncio
    async def test_send_message_empty_body_raises(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.room_send = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        with pytest.raises(ValueError, match="body"):
            await wrapper.send_message(
                room_id="!room:example.com",
                body="",
            )


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

class TestDownload:
    """Test MatrixClientWrapper.download()."""

    @pytest.mark.asyncio
    async def test_download_calls_client_download(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.download = AsyncMock(return_value=MagicMock(body=b"audio data"))
        wrapper._client = mock_client
        wrapper.is_connected = True

        result = await wrapper.download("https://matrix.example.com/media/abc123")

        mock_client.download.assert_called_once_with(
            "https://matrix.example.com/media/abc123",
        )
        assert result == b"audio data"

    @pytest.mark.asyncio
    async def test_download_raises_when_not_connected(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )

        with pytest.raises(RuntimeError, match="not connected"):
            await wrapper.download("https://example.com/media/abc")

    @pytest.mark.asyncio
    async def test_download_empty_url_raises(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.download = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        with pytest.raises(ValueError, match="url"):
            await wrapper.download("")


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------

class TestUpload:
    """Test MatrixClientWrapper.upload()."""

    @pytest.mark.asyncio
    async def test_upload_calls_client_upload(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_upload_response = MagicMock()
        mock_upload_response.content_uri = "mxc://example.com/abc123"
        mock_client.upload = AsyncMock(return_value=mock_upload_response)
        wrapper._client = mock_client
        wrapper.is_connected = True

        result = await wrapper.upload(b"audio data", "audio/ogg")

        mock_client.upload.assert_called_once()
        kwargs = mock_client.upload.call_args.kwargs
        assert kwargs["content_type"] == "audio/ogg"
        assert result == "mxc://example.com/abc123"

    @pytest.mark.asyncio
    async def test_upload_raises_when_not_connected(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )

        with pytest.raises(RuntimeError, match="not connected"):
            await wrapper.upload(b"data", "audio/ogg")

    @pytest.mark.asyncio
    async def test_upload_empty_data_raises(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.upload = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        with pytest.raises(ValueError, match="data"):
            await wrapper.upload(b"", "audio/ogg")

    @pytest.mark.asyncio
    async def test_upload_empty_mime_raises(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        wrapper = MatrixClientWrapper(
            homeserver, user, password, device_name,
        )
        mock_client = MagicMock()
        mock_client.upload = AsyncMock()
        wrapper._client = mock_client
        wrapper.is_connected = True

        with pytest.raises(ValueError, match="mime_type"):
            await wrapper.upload(b"data", "")


# ---------------------------------------------------------------------------
# Context Manager
# ---------------------------------------------------------------------------

class TestContextManager:
    """Test MatrixClientWrapper async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_connects_on_enter(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        mock_client = MagicMock()
        mock_client.set_push_encrypted_to_device = MagicMock()
        mock_client.close = AsyncMock()

        with patch(
            "bot.matrix.client.AsyncClient",
            return_value=mock_client,
        ):
            async with MatrixClientWrapper(
                homeserver, user, password, device_name,
            ) as wrapper:
                assert wrapper.is_connected is True

    @pytest.mark.asyncio
    async def test_context_manager_disconnects_on_exit(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        mock_client = MagicMock()
        mock_client.set_push_encrypted_to_device = MagicMock()
        mock_client.close = AsyncMock()

        with patch(
            "bot.matrix.client.AsyncClient",
            return_value=mock_client,
        ):
            async with MatrixClientWrapper(
                homeserver, user, password, device_name,
            ) as wrapper:
                pass

        assert wrapper.is_connected is False
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_disconnects_on_error(
        self, homeserver, user, password, device_name,
    ):
        from bot.matrix.client import MatrixClientWrapper

        mock_client = MagicMock()
        mock_client.set_push_encrypted_to_device = MagicMock()
        mock_client.close = AsyncMock()

        with patch(
            "bot.matrix.client.AsyncClient",
            return_value=mock_client,
        ):
            with pytest.raises(ValueError, match="boom"):
                async with MatrixClientWrapper(
                    homeserver, user, password, device_name,
                ) as wrapper:
                    raise ValueError("boom")

        assert wrapper.is_connected is False
        mock_client.close.assert_called_once()
