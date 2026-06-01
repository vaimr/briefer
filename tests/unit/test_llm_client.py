"""Tests for ``worker.llm_client.LLMClient``."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from worker.llm_client import LLMClient

# Patch target: llm_client.py imports `requests` at module level,
# so we must patch where it is looked up, not the top-level module.
_PATCH_TARGET = "worker.llm_client.requests.post"


@pytest.fixture
def client():
    """Return a default LLMClient instance."""
    return LLMClient(api_url="http://localhost:8080/v1", model_name="test-model")


# ── Initialization ────────────────────────────────────────────────


def test_client_initializes_with_config():
    """LLMClient stores api_url and model_name from constructor."""
    c = LLMClient(api_url="http://example.com/v1", model_name="my-model")
    assert c.api_url == "http://example.com/v1"
    assert c.model_name == "my-model"
    assert c.headers == {"Content-Type": "application/json"}
    assert c.MAX_SUMMARY_LENGTH == 2000
    assert c.MAX_TRANSCRIPTION_LENGTH == 4000
    assert c.MAX_RETRIES == 3
    assert c.RETRY_DELAY == 2
    assert c.REQUEST_TIMEOUT == 60


# ── Empty / whitespace input ──────────────────────────────────────


def test_summarize_empty_text_returns_default(client):
    """Empty or whitespace-only transcription returns the default message."""
    assert client.summarize("") == "Нет данных для саммари"
    assert client.summarize("   ") == "Нет данных для саммари"
    assert client.summarize("\n\t") == "Нет данных для саммари"


# ── Successful summarization ──────────────────────────────────────


def test_summarize_returns_text(client):
    """Successful API call returns the summary text from the response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "This is a summary."}}],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = client.summarize("Some transcription text here")

    assert result == "This is a summary."


# ── Length truncation ─────────────────────────────────────────────


def test_summarize_truncates_long_text(client):
    """Transcription longer than 4000 chars is truncated before sending."""
    long_text = "x" * 5000
    captured_payload = {}

    def capture_post(*args, **kwargs):
        captured_payload.update(kwargs.get("json", {}))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "summary"}}]}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    with patch(_PATCH_TARGET, side_effect=capture_post):
        client.summarize(long_text)

    user_msg = captured_payload["messages"][1]["content"]
    actual_text = user_msg.split("\n\n", 1)[1]
    assert len(actual_text) == 4000


def test_summarize_truncates_summary_length(client):
    """Summary longer than 2000 chars is truncated before returning."""
    long_summary = "y" * 3000
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": long_summary}}]}
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = client.summarize("Some text")

    assert len(result) == 2000


# ── Error handling ────────────────────────────────────────────────


def test_summarize_raises_on_empty_response(client):
    """Empty choices array raises ValueError."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []}
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        with pytest.raises(ValueError, match="empty choices"):
            client.summarize("Some text")


def test_summarize_raises_on_4xx(client):
    """4xx HTTP error raises ValueError immediately (no retry)."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad request"
    mock_response.json.return_value = {"error": "bad request"}
    http_exc = requests.exceptions.HTTPError(response=mock_response)

    with patch(_PATCH_TARGET, side_effect=http_exc):
        with pytest.raises(ValueError, match="LLM API error"):
            client.summarize("Some text")


def test_summarize_retries_on_5xx(client):
    """5xx errors trigger retries up to MAX_RETRIES times."""
    call_count = 0

    def mock_post(*a, **k):
        nonlocal call_count
        call_count += 1

        mock_resp = MagicMock()
        if call_count >= client.MAX_RETRIES:
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        else:
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            mock_resp.json.return_value = {}

        mock_resp.raise_for_status.return_value = None
        return mock_resp

    with patch(_PATCH_TARGET, side_effect=mock_post):
        result = client.summarize("text")

    assert result == "ok"
    assert call_count == client.MAX_RETRIES


def test_summarize_retries_on_connection_error(client):
    """ConnectionError triggers retries up to MAX_RETRIES times."""
    call_count = 0

    def mock_post(*a, **k):
        nonlocal call_count
        call_count += 1

        if call_count >= client.MAX_RETRIES:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        raise requests.exceptions.ConnectionError("connection refused")

    with patch(_PATCH_TARGET, side_effect=mock_post):
        result = client.summarize("text")

    assert result == "ok"
    assert call_count == client.MAX_RETRIES


def test_summarize_raises_after_3_retries(client):
    """Three consecutive ConnectionErrors raise ValueError."""
    call_count = 0

    def mock_post(*a, **k):
        nonlocal call_count
        call_count += 1
        raise requests.exceptions.ConnectionError("connection refused")

    with patch(_PATCH_TARGET, side_effect=mock_post):
        with pytest.raises(ValueError, match="connection failed after retries"):
            client.summarize("text")

    assert call_count == client.MAX_RETRIES
