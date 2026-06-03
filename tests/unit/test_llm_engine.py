"""Tests for ``worker.llm_engine.LLMAPI``."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from worker.llm_engine import LLMAPI

_PATCH_TARGET = "worker.llm_engine.requests.post"


@pytest.fixture
def llm():
    """Return a default LLMAPI instance."""
    return LLMAPI(api_url="http://localhost:8080/v1", model="test-model")


# ── chat() with regular model ─────────────────────────────────────


def test_chat_returns_content_from_regular_model(llm):
    """Regular model returns content in 'content' field."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello, world!"}}],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.chat("system prompt", "user content")

    assert result == "Hello, world!"


# ── chat() with reasoning model ───────────────────────────────────


def test_chat_falls_back_to_reasoning_content(llm):
    """Reasoning model returns empty 'content', falls back to 'reasoning_content'."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "",
                "reasoning_content": "This is a reasoning response.",
            }
        }],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.chat("system prompt", "user content")

    assert result == "This is a reasoning response."


def test_chat_prefers_content_over_reasoning_content(llm):
    """When both 'content' and 'reasoning_content' exist, prefer 'content'."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "Regular response",
                "reasoning_content": "Reasoning content",
            }
        }],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.chat("system prompt", "user content")

    assert result == "Regular response"


# ── summarize() ───────────────────────────────────────────────────


def test_summarize_returns_text(llm):
    """summarize() calls chat with SUMMARIZE_PROMPT and returns result."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Meeting summary text"}}],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.summarize("Some transcription text")

    assert result == "Meeting summary text"


def test_summarize_with_reasoning_model(llm):
    """summarize() works with reasoning models that return reasoning_content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "",
                "reasoning_content": "Summarized from reasoning",
            }
        }],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.summarize("Some transcription text")

    assert result == "Summarized from reasoning"


# ── check_risks() ─────────────────────────────────────────────────


def test_check_risks_parses_json(llm):
    """check_risks() parses JSON response and returns dict."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": '{"is_risky": true, "risk_level": "high", "categories": ["violation"], "details": [], "summary": "Risk detected"}'
            }
        }],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.check_risks("transcript with risky content")

    assert result["is_risky"] is True
    assert result["risk_level"] == "high"
    assert "violation" in result["categories"]


def test_check_risks_strips_code_blocks(llm):
    """check_risks() strips markdown code blocks from response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "```json\n{\"is_risky\": false, \"risk_level\": \"none\", \"categories\": [], \"details\": [], \"summary\": \"\"}\n```"
            }
        }],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.check_risks("safe transcript")

    assert result["is_risky"] is False
    assert result["risk_level"] == "none"


def test_check_risks_returns_default_on_empty_content(llm):
    """check_risks() returns default dict when LLM returns empty content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": ""}}],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.check_risks("transcript")

    assert result == {"is_risky": False, "risk_level": "none", "categories": [], "details": [], "summary": ""}


def test_check_risks_returns_default_on_parse_error(llm):
    """check_risks() returns default dict on JSON parse error."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "not valid json"}}],
    }
    mock_response.raise_for_status.return_value = None

    with patch(_PATCH_TARGET, return_value=mock_response):
        result = llm.check_risks("transcript")

    assert result["is_risky"] is False
    assert "Ошибка парсинга" in result["summary"]


# ── HTTP errors ───────────────────────────────────────────────────


def test_chat_raises_on_http_error(llm):
    """chat() raises HTTPError on non-200 response."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.json.return_value = {"error": "server error"}
    http_exc = requests.exceptions.HTTPError(response=mock_response)

    with patch(_PATCH_TARGET, side_effect=http_exc):
        with pytest.raises(requests.exceptions.HTTPError):
            llm.chat("system", "user")
