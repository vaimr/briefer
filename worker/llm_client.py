"""LLM API client with retry logic for summarization.

Provides ``LLMClient`` — a synchronous OpenAI-compatible API wrapper
that retries on transient failures and enforces length limits.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """Synchronous client for OpenAI-compatible LLM APIs.

    Attributes:
        MAX_SUMMARY_LENGTH: Maximum allowed summary length in characters.
        MAX_TRANSCRIPTION_LENGTH: Maximum transcription length before truncation.
        MAX_RETRIES: Number of retry attempts on transient failures.
        RETRY_DELAY: Seconds to wait between retries.
        REQUEST_TIMEOUT: Seconds to wait for a response.
    """

    MAX_SUMMARY_LENGTH = 2000
    MAX_TRANSCRIPTION_LENGTH = 4000
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    REQUEST_TIMEOUT = 60

    def __init__(self, api_url: str, model_name: str) -> None:
        """Initialize the LLM client.

        Args:
            api_url: Base URL of the OpenAI-compatible API (e.g. ``http://faex:8080/v1``).
            model_name: Name of the model to use (e.g. ``qwen3.6-a3b-mtp:35b``).
        """
        self.api_url: str = api_url
        self.model_name: str = model_name
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    def summarize(self, transcription_text: str) -> str:
        """Generate a summary from transcription text.

        Args:
            transcription_text: Raw transcription text to summarize.

        Returns:
            Summary text truncated to ``MAX_SUMMARY_LENGTH`` characters.

        Raises:
            ValueError: On 4xx errors, empty response, or after all retries exhausted.
        """
        if not transcription_text or not transcription_text.strip():
            return "Нет данных для саммари"

        text: str = transcription_text
        if len(text) > self.MAX_TRANSCRIPTION_LENGTH:
            text = text[: self.MAX_TRANSCRIPTION_LENGTH]

        payload: dict = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты — ассистент для краткого изложения аудио-транскрипций.",
                },
                {
                    "role": "user",
                    "content": f"Сделай краткое саммари этого текста (до {self.MAX_SUMMARY_LENGTH} символов):\n\n{text}",
                },
            ],
            "max_tokens": 1500,
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.post(
                    f"{self.api_url}/chat/completions",
                    json=payload,
                    headers=self.headers,
                    timeout=self.REQUEST_TIMEOUT,
                )

                if response.status_code >= 500:
                    if attempt == self.MAX_RETRIES - 1:
                        raise ValueError(
                            f"LLM API server error {response.status_code}: {response.text}"
                        )
                    logger.warning(
                        "LLM API returned %d, retrying... (attempt %d/%d)",
                        response.status_code,
                        attempt + 1,
                        self.MAX_RETRIES,
                    )
                    time.sleep(self.RETRY_DELAY)
                    continue

                response.raise_for_status()

                data = response.json()
                choices = data.get("choices")
                if not choices:
                    raise ValueError("LLM API returned empty choices")

                summary: str = choices[0]["message"]["content"]
                return summary[: self.MAX_SUMMARY_LENGTH]

            except requests.exceptions.HTTPError as exc:
                # 4xx error — do not retry
                raise ValueError(f"LLM API error: {exc}") from exc

            except requests.exceptions.ConnectionError:
                if attempt == self.MAX_RETRIES - 1:
                    raise ValueError("LLM API connection failed after retries") from None
                logger.warning(
                    "Connection error, retrying... (attempt %d/%d)",
                    attempt + 1,
                    self.MAX_RETRIES,
                )
                time.sleep(self.RETRY_DELAY)

            except requests.exceptions.Timeout:
                if attempt == self.MAX_RETRIES - 1:
                    raise ValueError("LLM API request timed out after retries") from None
                logger.warning(
                    "Timeout, retrying... (attempt %d/%d)",
                    attempt + 1,
                    self.MAX_RETRIES,
                )
                time.sleep(self.RETRY_DELAY)

        # Should not reach here, but type-system safety net
        raise ValueError("LLM API request failed after all retries")
