"""Mock LLM API for testing.

Provides a fake LLM engine that returns canned summarization and
risk detection results without making real HTTP requests.
"""

import json
from unittest.mock import MagicMock, patch


class FakeLLMAPI:
    """Fake LLM API for testing.

    Mimics llm_engine.LLMAPI interface:
    - chat(system_prompt, user_content, temperature, max_tokens) -> str
    - summarize(transcript) -> str
    - check_risks(transcript) -> dict

    Returns canned responses by default. Can be configured
    with custom responses via set_responses().
    """

    DEFAULT_SUMMARY = (
        "Саммари встречи\n\n"
        "Дата: не указано\n"
        "Участники: не определены\n"
        "Тема: Обсуждение проекта\n\n"
        "Ключевые пункты:\n"
        "- Обсужden timeline\n"
        "- Определены deliverables\n"
        "- Дедлайн: следующая пятница"
    )

    DEFAULT_RISKS = {
        "is_risky": False,
        "risk_level": "none",
        "categories": [],
        "details": [],
        "summary": "Опасных обсуждений не обнаружено.",
    }

    def __init__(self, api_url: str = "http://faex:8080/v1", model: str = "qwen3.6-a3b-mtp:35b"):
        self.api_url = api_url
        self.model = model
        self._custom_summary: str | None = None
        self._custom_risks: dict | None = None
        self._chat_calls: list[dict] = []

    def set_responses(self, summary: str, risks: dict) -> None:
        """Set custom summary and risks for future calls."""
        self._custom_summary = summary
        self._custom_risks = risks

    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.1, max_tokens: int = 1500) -> str:
        """Return canned summary or risks depending on prompt content."""
        self._chat_calls.append({
            "system_prompt": system_prompt,
            "user_content": user_content[:200],
            "temperature": temperature,
        })
        if "саммари" in system_prompt.lower() or "summary" in system_prompt.lower():
            return self._custom_summary or self.DEFAULT_SUMMARY
        if "риск" in system_prompt.lower() or "risk" in system_prompt.lower():
            return json.dumps(self._custom_risks or self.DEFAULT_RISKS)
        return self._custom_summary or self.DEFAULT_SUMMARY

    def summarize(self, transcript: str) -> str:
        """Return canned summary."""
        return self.chat("", transcript, temperature=0.1, max_tokens=1500)

    def check_risks(self, transcript: str) -> dict:
        """Return canned risks."""
        return json.loads(self.chat("", transcript, temperature=0.0, max_tokens=1000))

    def get_chat_calls(self) -> list[dict]:
        """Return all chat calls made."""
        return list(self._chat_calls)

    def reset(self) -> None:
        """Reset all state."""
        self._chat_calls.clear()
        self._custom_summary = None
        self._custom_risks = None


def mock_llm_api(
    api_url: str = "http://faex:8080/v1",
    model: str = "qwen3.6-a3b-mtp:35b",
    summary: str = "",
    risks: dict | None = None,
):
    """Factory fixture to create a FakeLLMAPI.

    Example:
        llm = mock_llm_api()
        result = llm.summarize("transcript text")
        assert "Саммари" in result
    """
    api = FakeLLMAPI(api_url=api_url, model=model)
    if summary or risks:
        api.set_responses(summary or FakeLLMAPI.DEFAULT_SUMMARY, risks or FakeLLMAPI.DEFAULT_RISKS)
    return api


def mock_requests_post(status_code: int = 200, json_response: dict | None = None):
    """Create a mock for requests.post (used in health checks).

    Example:
        with mock_requests_post(status_code=200):
            # health check passes
    """
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_response or {"choices": [{"message": {"content": "ok"}}]}
    return patch("requests.post", return_value=mock_resp)
