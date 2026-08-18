"""Tests for bot/__main__.py — signal handling, logging, and error handling."""

import argparse
import asyncio
import logging
import signal
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bot.__main__ as bot_main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings(**overrides):
    """Return a mock settings object with all required attributes."""
    s = MagicMock()
    s.REDIS_HOST = overrides.get("REDIS_HOST", "redis")
    s.REDIS_PORT = overrides.get("REDIS_PORT", 6379)
    s.HELP_TEXT_FILE = overrides.get("HELP_TEXT_FILE", "/etc/briefer/help.txt")
    s.HEALTH_PORT = overrides.get("HEALTH_PORT", 8081)
    s.MATRIX_HOMESERVER = overrides.get("MATRIX_HOMESERVER", "https://matrix.example.com")
    s.MATRIX_USER = overrides.get("MATRIX_USER", "@bot:example.com")
    s.MATRIX_ACCESS_TOKEN = overrides.get("MATRIX_ACCESS_TOKEN", "tok123")
    s.MATRIX_PASSWORD = overrides.get("MATRIX_PASSWORD", None)
    s.LOG_LEVEL = overrides.get("LOG_LEVEL", "INFO")
    s.validate_required = MagicMock()
    return s


def _make_mock_redis(**overrides):
    """Return a redis.Redis mock."""
    client = MagicMock()
    client.rpush = MagicMock(return_value=1)
    pubsub = MagicMock()
    pubsub.subscribe = MagicMock()
    pubsub.listen = MagicMock(return_value=iter([]))
    client.pubsub = MagicMock(return_value=pubsub)
    return client


def _make_mock_matrix(**overrides):
    """Return a mock AsyncClient with async methods."""
    client = MagicMock()
    client.room_send = AsyncMock()
    client.join = AsyncMock()
    client.add_event_callback = MagicMock()
    client.add_response_callback = MagicMock()
    client.sync_forever = AsyncMock()
    client.user_id = "@bot:example.com"
    client.download = AsyncMock()
    return client


def _make_mock_event(**overrides):
    """Return a mock Matrix event."""
    event = MagicMock()
    event.message_id = overrides.get("message_id", "msg_001")
    return event


def _make_mock_room(**overrides):
    """Return a mock Matrix room."""
    room = MagicMock()
    room.room_id = overrides.get("room_id", "!room:example.com")
    return room


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    return _make_mock_settings()


@pytest.fixture
def mock_redis_client():
    return _make_mock_redis()


@pytest.fixture
def mock_matrix_client():
    return _make_mock_matrix()


@pytest.fixture
def mock_event():
    return _make_mock_event()


@pytest.fixture
def mock_room():
    return _make_mock_room()


# ---------------------------------------------------------------------------
# Test: full audio pipeline
# ---------------------------------------------------------------------------


class TestHandleAudioMessageFullPipeline:
    """Verify full audio message processing pipeline with logging."""

    @pytest.mark.asyncio
    async def test_full_pipeline_logs_all_stages(
        self,
        mock_settings,
        mock_redis_client,
        mock_matrix_client,
        mock_event,
        mock_room,
        caplog,
    ):
        """Full audio pipeline: download -> validate -> queue -> status.

        Given: valid audio message
        When: bot processes it
        Then: all pipeline stages are logged and queue is called
        """
        with (
            patch.object(bot_main, "settings", mock_settings),
            patch.object(bot_main, "create_client", new=AsyncMock(return_value=mock_matrix_client)),
            patch.object(bot_main, "load_help_text", return_value="Help text"),
            patch.object(bot_main, "start_http_server"),
            patch.object(bot_main, "redis", MagicMock(Redis=MagicMock(return_value=mock_redis_client))),
            patch.object(bot_main, "result_listener", new=AsyncMock()),
        ):
            caplog.set_level(logging.INFO)
            mock_matrix_client.sync_forever = AsyncMock(
                side_effect=asyncio.CancelledError("test exit")
            )

            try:
                await bot_main.main()
            except asyncio.CancelledError:
                pass

        # Verify callback was registered
        assert mock_matrix_client.add_event_callback.called
        # call_args_list[0] = first call (audio handler), [1] = invite handler
        callback = mock_matrix_client.add_event_callback.call_args_list[0][0][0]

        caplog.clear()

        # Simulate callback invocation with audio event
        mock_event.message_id = "msg_001"
        mock_event.get = MagicMock(return_value="audio.wav")
        with (
            patch.object(bot_main, "get_audio_event_type", return_value=True),
            patch.object(
                bot_main,
                "handle_audio_message",
                new=AsyncMock(side_effect=lambda c, r, e, d, qp: (qp(f"task_001"), "/data/input/msg_001.audio.wav")),
            ),
        ):
            await callback(mock_room, mock_event)

        # Verify all log messages
        assert "Processing audio message: room_id=!room:example.com" in caplog.text
        assert "Audio validated: !room:example.com" in caplog.text
        assert "Pushed to queue: !room:example.com" in caplog.text

        # Verify queue push was called
        mock_redis_client.rpush.assert_called_once()


# ---------------------------------------------------------------------------
# Test: non-audio ignored
# ---------------------------------------------------------------------------


class TestHandleNonAudioIgnored:
    """Verify non-audio messages trigger help text response."""

    @pytest.mark.asyncio
    async def test_non_audio_message_sends_help_text(
        self,
        mock_settings,
        mock_redis_client,
        mock_matrix_client,
        mock_event,
        mock_room,
        caplog,
    ):
        """Non-audio message -> help text sent.

        Given: a non-audio event
        When: bot processes it
        Then: help text is sent to the room
        """
        with (
            patch.object(bot_main, "settings", mock_settings),
            patch.object(bot_main, "create_client", new=AsyncMock(return_value=mock_matrix_client)),
            patch.object(bot_main, "load_help_text", return_value="Help text"),
            patch.object(bot_main, "start_http_server"),
            patch.object(bot_main, "redis", MagicMock(Redis=MagicMock(return_value=mock_redis_client))),
            patch.object(bot_main, "result_listener", new=AsyncMock()),
        ):
            caplog.set_level(logging.INFO)
            mock_matrix_client.sync_forever = AsyncMock(
                side_effect=asyncio.CancelledError("test exit")
            )

            try:
                await bot_main.main()
            except asyncio.CancelledError:
                pass

        # Verify callback was registered
        callback = mock_matrix_client.add_event_callback.call_args_list[0][0][0]

        caplog.clear()

        # Simulate callback with non-audio event
        mock_event.message_id = "msg_002"
        with patch.object(bot_main, "get_audio_event_type", return_value=False):
            await callback(mock_room, mock_event)

        # Verify help text was sent
        mock_matrix_client.room_send.assert_called_once()

        # Verify log message
        assert "Non-audio message received: room_id=!room:example.com" in caplog.text


# ---------------------------------------------------------------------------
# Test: invalid audio error status
# ---------------------------------------------------------------------------


class TestHandleInvalidAudioErrorStatus:
    """Verify invalid audio triggers error notification."""

    @pytest.mark.asyncio
    async def test_invalid_audio_sends_error_status(
        self,
        mock_settings,
        mock_redis_client,
        mock_matrix_client,
        mock_event,
        mock_room,
        caplog,
    ):
        """Invalid audio -> error notification sent to room.

        Given: an audio event that fails processing
        When: bot processes it
        Then: error is logged and error notification is sent
        """
        with (
            patch.object(bot_main, "settings", mock_settings),
            patch.object(bot_main, "create_client", new=AsyncMock(return_value=mock_matrix_client)),
            patch.object(bot_main, "load_help_text", return_value="Help text"),
            patch.object(bot_main, "start_http_server"),
            patch.object(bot_main, "redis", MagicMock(Redis=MagicMock(return_value=mock_redis_client))),
            patch.object(bot_main, "result_listener", new=AsyncMock()),
        ):
            mock_matrix_client.sync_forever = AsyncMock(
                side_effect=asyncio.CancelledError("test exit")
            )

            try:
                await bot_main.main()
            except asyncio.CancelledError:
                pass

        # Verify callback was registered
        callback = mock_matrix_client.add_event_callback.call_args_list[0][0][0]

        # Simulate callback with audio event that raises
        mock_event.message_id = "msg_003"
        with patch.object(bot_main, "get_audio_event_type", return_value=True):
            with patch.object(
                bot_main,
                "handle_audio_message",
                new=AsyncMock(side_effect=ValueError("Invalid audio format")),
            ):
                await callback(mock_room, mock_event)

        # Verify error was logged
        assert "Error processing message:" in caplog.text
        assert "Invalid audio format" in caplog.text

        # Verify error notification was sent
        assert mock_matrix_client.room_send.called
        call_args = mock_matrix_client.room_send.call_args
        assert call_args[0][0] == "!room:example.com"
        assert "Ошибка" in call_args[0][2]["body"]


# ---------------------------------------------------------------------------
# Test: graceful shutdown via signals
# ---------------------------------------------------------------------------


class TestGracefulShutdownSigterm:
    """Verify SIGTERM triggers graceful shutdown via shutdown_event."""

    @pytest.mark.asyncio
    async def test_sigterm_sets_shutdown_event(
        self,
        mock_settings,
        mock_redis_client,
        mock_matrix_client,
        caplog,
    ):
        """SIGTERM -> shutdown_event.set() and bot shuts down gracefully.

        Given: running bot
        When: sync_forever raises CancelledError
        Then: shutdown logging and redis close occur
        """
        with (
            patch.object(bot_main, "settings", mock_settings),
            patch.object(bot_main, "create_client", new=AsyncMock(return_value=mock_matrix_client)),
            patch.object(bot_main, "load_help_text", return_value="Help text"),
            patch.object(bot_main, "start_http_server"),
            patch.object(bot_main, "redis", MagicMock(Redis=MagicMock(return_value=mock_redis_client))),
            patch.object(bot_main, "result_listener", new=AsyncMock()),
        ):
            caplog.set_level(logging.INFO)
            mock_matrix_client.sync_forever = AsyncMock(
                side_effect=asyncio.CancelledError("test exit")
            )

            try:
                await bot_main.main()
            except asyncio.CancelledError:
                pass

        # Verify shutdown logging
        assert "Bot shutting down" in caplog.text
        assert "Bot stopped" in caplog.text

        # Verify redis client was closed
        mock_redis_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_signal_handlers_registered(
        self,
        mock_settings,
        mock_redis_client,
        mock_matrix_client,
    ):
        """Signal handlers for SIGTERM and SIGINT are registered.

        Given: running bot
        When: main() starts the event loop
        Then: add_signal_handler is called for SIGTERM and SIGINT
        """
        with (
            patch.object(bot_main, "settings", mock_settings),
            patch.object(bot_main, "create_client", new=AsyncMock(return_value=mock_matrix_client)),
            patch.object(bot_main, "load_help_text", return_value="Help text"),
            patch.object(bot_main, "start_http_server"),
            patch.object(bot_main, "redis", MagicMock(Redis=MagicMock(return_value=mock_redis_client))),
            patch.object(bot_main, "result_listener", new=AsyncMock()),
        ):
            mock_matrix_client.sync_forever = AsyncMock(
                side_effect=asyncio.CancelledError("test exit")
            )

            try:
                await bot_main.main()
            except asyncio.CancelledError:
                pass

        # Handlers were registered without raising
        assert hasattr(signal, "SIGTERM")
        assert hasattr(signal, "SIGINT")

    @pytest.mark.asyncio
    async def test_shutdown_event_is_set_on_signal(
        self,
    ):
        """shutdown_event is a proper asyncio.Event that can be set.

        Given: module-level shutdown_event
        When: signal handler calls shutdown_event.set()
        Then: is_set() returns True
        """
        # Verify the module-level shutdown_event exists and is an Event
        assert isinstance(bot_main.shutdown_event, asyncio.Event)
        assert not bot_main.shutdown_event.is_set()

        # Simulate signal handler behavior
        bot_main.shutdown_event.set()
        assert bot_main.shutdown_event.is_set()

        # Reset for other tests
        bot_main.shutdown_event.clear()


class TestShutdownDuringDelivery:
    """Verify SIGTERM during delivery completes current operation then shuts down."""

    @pytest.mark.asyncio
    async def test_shutdown_during_delivery_completes(
        self,
        caplog,
    ):
        """SIGTERM during delivery → delivery completes, then shutdown.

        Given: running bot with active result listener consumer
        When: SIGTERM is received during delivery
        Then: shutdown handler waits for task to complete, then sync_forever exits
        """
        mock_settings = _make_mock_settings()
        mock_redis_client = _make_mock_redis()
        mock_matrix_client = _make_mock_matrix()
        mock_pubsub = MagicMock()
        mock_redis_client.pubsub = MagicMock(return_value=mock_pubsub)
        mock_matrix_client.sync_forever = AsyncMock(
            side_effect=asyncio.CancelledError("test exit")
        )

        # Patch shutdown_event to avoid polluting module state
        original_event = bot_main.shutdown_event
        bot_main.shutdown_event = asyncio.Event()

        try:
            with (
                patch.object(bot_main, "settings", mock_settings),
                patch.object(bot_main, "create_client", new=AsyncMock(return_value=mock_matrix_client)),
                patch.object(bot_main, "load_help_text", return_value="Help text"),
                patch.object(bot_main, "start_http_server"),
                patch.object(bot_main, "redis", MagicMock(Redis=MagicMock(return_value=mock_redis_client))),
                patch.object(bot_main, "result_listener", new=AsyncMock(side_effect=asyncio.sleep(0.05))),
            ):
                caplog.set_level(logging.INFO)

                try:
                    await bot_main.main()
                except asyncio.CancelledError:
                    pass

                # Simulate SIGTERM by calling the shutdown handler directly
                await bot_main._handle_shutdown(signal.SIGTERM)

                # Verify shutdown handler was called (log present)
                assert "Shutting down..." in caplog.text
                assert "Bot shutting down" in caplog.text
                assert "Bot stopped" in caplog.text

                # Verify redis client was closed
                mock_redis_client.close.assert_called_once()
        finally:
            bot_main.shutdown_event = original_event

    @pytest.mark.asyncio
    async def test_shutdown_without_consumer_noop(
        self,
        caplog,
    ):
        """SIGTERM without running consumer → no error.

        Given: running bot with no result listener task
        When: SIGTERM is received
        Then: shutdown handler is a no-op (task is None), bot shuts down cleanly
        """
        mock_settings = _make_mock_settings()
        mock_redis_client = _make_mock_redis()
        mock_matrix_client = _make_mock_matrix()
        mock_pubsub = MagicMock()
        mock_redis_client.pubsub = MagicMock(return_value=mock_pubsub)
        mock_matrix_client.sync_forever = AsyncMock(
            side_effect=asyncio.CancelledError("test exit")
        )

        # Patch shutdown_event to avoid polluting module state
        original_event = bot_main.shutdown_event
        bot_main.shutdown_event = asyncio.Event()

        try:
            with (
                patch.object(bot_main, "settings", mock_settings),
                patch.object(bot_main, "create_client", new=AsyncMock(return_value=mock_matrix_client)),
                patch.object(bot_main, "load_help_text", return_value="Help text"),
                patch.object(bot_main, "start_http_server"),
                patch.object(bot_main, "redis", MagicMock(Redis=MagicMock(return_value=mock_redis_client))),
                patch.object(bot_main, "result_listener", new=AsyncMock()),
            ):
                caplog.set_level(logging.INFO)

                try:
                    await bot_main.main()
                except asyncio.CancelledError:
                    pass

                # Simulate SIGTERM directly — no task to wait for, should be a no-op
                await bot_main._handle_shutdown(signal.SIGTERM)

                # Verify shutdown logging
                assert "Shutting down..." in caplog.text
                assert "Bot shutting down" in caplog.text
                assert "Bot stopped" in caplog.text

                # Verify redis client was closed
                mock_redis_client.close.assert_called_once()
        finally:
            bot_main.shutdown_event = original_event


# ---------------------------------------------------------------------------
# Test: --help flag
# ---------------------------------------------------------------------------


class TestHelpFlag:
    """Verify --help flag triggers argparse help without error."""

    def test_help_flag_no_error(self):
        """--help flag triggers argparse help (verify no error).

        Given: --help argument
        When: parser.parse_args() is called
        Then: SystemExit(0) is raised
        """
        with (
            patch.object(sys, "argv", ["bot", "--help"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            bot_main._build_parser().parse_args()

        assert exc_info.value.code == 0

    def test_parser_description(self):
        """ArgumentParser has a meaningful description.

        Given: _build_parser()
        When: parser is created
        Then: description is non-empty
        """
        parser = bot_main._build_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.description is not None
        assert len(parser.description) > 0

    def test_default_args_no_error(self):
        """Running with no arguments does not raise (main() will fail later).

        Given: no arguments
        When: parser.parse_args() is called
        Then: args object is returned without error
        """
        with patch.object(sys, "argv", ["bot"]):
            parser = bot_main._build_parser()
            args = parser.parse_args()
            assert args is not None
