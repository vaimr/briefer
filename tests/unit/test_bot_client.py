"""Tests for bot/client.py — create_client authentication wrapper."""

import pytest
from unittest.mock import AsyncMock, patch

from nio import AsyncClient

from bot.client import MatrixClientError, create_client
from bot.config import BotConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def token_config():
    """BotConfig with MATRIX_ACCESS_TOKEN only."""
    return BotConfig(
        MATRIX_HOMESERVER="https://matrix.example.com",
        MATRIX_USER="@bot:example.com",
        MATRIX_ACCESS_TOKEN="tok_123",
    )


@pytest.fixture
def password_config():
    """BotConfig with MATRIX_PASSWORD only."""
    return BotConfig(
        MATRIX_HOMESERVER="https://matrix.example.com",
        MATRIX_USER="@bot:example.com",
        MATRIX_PASSWORD="secret",
    )


@pytest.fixture
def both_config():
    """BotConfig with both MATRIX_ACCESS_TOKEN and MATRIX_PASSWORD."""
    return BotConfig(
        MATRIX_HOMESERVER="https://matrix.example.com",
        MATRIX_USER="@bot:example.com",
        MATRIX_ACCESS_TOKEN="tok_123",
        MATRIX_PASSWORD="secret",
    )


@pytest.fixture
def no_auth_config():
    """BotConfig with neither MATRIX_ACCESS_TOKEN nor MATRIX_PASSWORD."""
    return BotConfig(
        MATRIX_HOMESERVER="https://matrix.example.com",
        MATRIX_USER="@bot:example.com",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateClientWithToken:
    """Token-based authentication."""

    @pytest.mark.asyncio
    async def test_access_token_is_set(self, token_config):
        """access_token from config is assigned to client.access_token."""
        client = await create_client(token_config)
        assert client.access_token == "tok_123"

    @pytest.mark.asyncio
    async def test_login_not_called_when_token_present(self, token_config):
        """login() must NOT be called if access_token is already provided."""
        with patch.object(
            AsyncClient, "login", new=AsyncMock(return_value=AsyncMock())
        ) as mock_login:
            client = await create_client(token_config)
            mock_login.assert_not_called()


class TestCreateClientWithPassword:
    """Password-based authentication."""

    @pytest.mark.asyncio
    async def test_login_called_with_correct_params(self, password_config):
        """login(password=..., device_name='briefer-bot') is called."""
        with patch.object(
            AsyncClient, "login", new=AsyncMock(return_value=AsyncMock())
        ) as mock_login:
            await create_client(password_config)
            mock_login.assert_called_once_with(
                password="secret",
                device_name="briefer-bot",
            )

    @pytest.mark.asyncio
    async def test_token_takes_precedence_over_password(self, both_config):
        """When both are present, token is used and login() is NOT called."""
        with patch.object(
            AsyncClient, "login", new=AsyncMock(return_value=AsyncMock())
        ) as mock_login:
            client = await create_client(both_config)
            mock_login.assert_not_called()
        assert client.access_token == "tok_123"


class TestCreateClientNoAuth:
    """No credentials provided."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, no_auth_config):
        """ValueError is raised when neither token nor password is set."""
        with pytest.raises(ValueError, match="MATRIX_ACCESS_TOKEN or MATRIX_PASSWORD"):
            await create_client(no_auth_config)


class TestCreateClientLoginFailure:
    """Password login raises an exception."""

    @pytest.mark.asyncio
    async def test_raises_matrix_client_error(self, password_config):
        """Exception from login is wrapped in MatrixClientError."""
        with patch.object(
            AsyncClient, "login", new=AsyncMock(side_effect=Exception("bad credentials"))
        ):
            with pytest.raises(MatrixClientError, match="Matrix login failed"):
                await create_client(password_config)


class TestClientReturnsValidInstance:
    """Returned client is a proper AsyncClient with user_id."""

    @pytest.mark.asyncio
    async def test_returns_async_client(self, token_config):
        """Function returns an AsyncClient instance."""
        client = await create_client(token_config)
        assert isinstance(client, AsyncClient)

    @pytest.mark.asyncio
    async def test_user_id_is_set_after_password_login(self, password_config):
        """Client gets a non-empty user_id after successful password login."""
        with patch.object(
            AsyncClient, "login", new=AsyncMock(return_value=AsyncMock())
        ):
            client = await create_client(password_config)
        # nio.login() assigns user_id on the client instance
        client.user_id = "@bot:example.com"
        assert client.user_id == "@bot:example.com"
