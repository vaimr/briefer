"""Tests for message handling methods in MatrixClientWrapper.

T2.1.3 — Add Matrix Message Handling
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
# EventFilter type
# ---------------------------------------------------------------------------

class TestEventFilter:
    """Test EventFilter type alias."""

    def test_event_filter_is_assignable(self):
        from bot.matrix.client import EventFilter

        def my_filter(event):
            return True

        # The type should be assignable
        f: EventFilter = my_filter
        assert f is my_filter


# ---------------------------------------------------------------------------
# add_filter
# ---------------------------------------------------------------------------

class TestAddFilter:
    """Test MatrixClientWrapper.add_filter()."""

    def test_add_filter_adds_filter(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        def my_filter(event):
            return True

        wrapper.add_filter(my_filter)

        assert len(wrapper._filters) == 1
        assert wrapper._filters[0] is my_filter

    def test_add_filter_multiple_filters(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        def filter1(event):
            return True

        def filter2(event):
            return False

        wrapper.add_filter(filter1)
        wrapper.add_filter(filter2)

        assert len(wrapper._filters) == 2
        assert wrapper._filters[0] is filter1
        assert wrapper._filters[1] is filter2

    def test_add_filter_preserves_order(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        results = []

        def filter1(event):
            results.append(1)
            return True

        def filter2(event):
            results.append(2)
            return True

        wrapper.add_filter(filter1)
        wrapper.add_filter(filter2)

        # Filters are applied in order
        wrapper._apply_filters("event")
        assert results == [1, 2]

    def test_add_filter_rejects_non_callable(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(TypeError, match="filter"):
            wrapper.add_filter("not a function")  # type: ignore


# ---------------------------------------------------------------------------
# handle_message
# ---------------------------------------------------------------------------

class TestHandleMessage:
    """Test MatrixClientWrapper.handle_message()."""

    def test_handle_message_returns_event_body(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = "Hello world"

        result = wrapper.handle_message(mock_event)

        assert result == "Hello world"

    def test_handle_message_returns_empty_body(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = ""

        result = wrapper.handle_message(mock_event)

        assert result == ""

    def test_handle_message_none_body(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = None

        result = wrapper.handle_message(mock_event)

        assert result is None

    def test_handle_message_no_args_raises(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        with pytest.raises(TypeError):
            wrapper.handle_message()  # type: ignore


# ---------------------------------------------------------------------------
# process_event
# ---------------------------------------------------------------------------

class TestProcessEvent:
    """Test MatrixClientWrapper.process_event()."""

    @pytest.mark.asyncio
    async def test_process_event_no_filters_calls_handler(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = "Hello"

        handler = MagicMock(return_value=None)
        result = await wrapper.process_event(mock_event, handler)

        handler.assert_called_once_with(mock_event)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_event_all_filters_pass(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = "Hello"

        def filter1(event):
            return True

        def filter2(event):
            return True

        wrapper.add_filter(filter1)
        wrapper.add_filter(filter2)

        handler = MagicMock(return_value="handled")

        result = await wrapper.process_event(mock_event, handler)

        handler.assert_called_once_with(mock_event)
        assert result == "handled"

    @pytest.mark.asyncio
    async def test_process_event_first_filter_fails(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = "Hello"

        def filter1(event):
            return False

        def filter2(event):
            return True

        wrapper.add_filter(filter1)
        wrapper.add_filter(filter2)

        handler = MagicMock(return_value="handled")

        result = await wrapper.process_event(mock_event, handler)

        handler.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_process_event_second_filter_fails(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = "Hello"

        def filter1(event):
            return True

        def filter2(event):
            return False

        wrapper.add_filter(filter1)
        wrapper.add_filter(filter2)

        handler = MagicMock(return_value="handled")

        result = await wrapper.process_event(mock_event, handler)

        handler.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_process_event_handler_exception_propagates(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = "Hello"

        def handler(event):
            raise ValueError("handler error")

        with pytest.raises(ValueError, match="handler error"):
            await wrapper.process_event(mock_event, handler)

    @pytest.mark.asyncio
    async def test_process_event_handler_return_value_passed_through(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = "Hello"

        def handler(event):
            return {"status": "ok", "data": "result"}

        result = await wrapper.process_event(mock_event, handler)

        assert result == {"status": "ok", "data": "result"}

    @pytest.mark.asyncio
    async def test_process_event_async_handler(self, wrapper):
        from bot.matrix.client import MatrixClientWrapper

        mock_event = MagicMock()
        mock_event.body = "Hello"

        async def async_handler(event):
            return "async result"

        result = await wrapper.process_event(mock_event, async_handler)

        assert result == "async result"
