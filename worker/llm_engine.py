"""LLM engine for summarization and risk detection."""

import json
import logging
import requests

logger = logging.getLogger(__name__)


SUMMARIZE_PROMPT = (
    "Ты — профессиональный ассистент для создания саммари встреч на русском языке. "
    "Проанализируй транскрипцию и создай структурированное саммари.\n\n"
    "Структура саммари:\n"
    "## Саммари встречи\n\n"
    "**Дата и время:** ...\n"
    "**Участники:** ...\n"
    "**Тема:** ...\n\n"
    "## Ключевые обсуждения\n\n"
    "- пункт 1\n"
    "- пункт 2\n\n"
    "## Задачи\n\n"
    "- задача 1\n\n"
    "## Дополнительные заметки\n\n"
    "...\n\n"
    "Правила:\n"
    "- Пиши на русском языке\n"
    "- Основывайся только на содержании транскрипции\n"
    "- Не выдумывай факты\n"
    "- Если информация не упоминается — напиши «не указано» или «не обсуждались»\n"
    "- Саммари должно быть информативным, но не перегруженным"
)

RISK_PROMPT = (
    "Ты — система безопасности, анализирующая транскрипции деловых встреч на наличие опасных тем.\n\n"
    "Задача: проанализировать транскрипцию и выявить упоминания следующих категорий:\n"
    "1. Нарушение закона — обсуждение действий, нарушающих УК, КоАП, ФЗ\n"
    "2. Коммерческая тайна — обсуждение разглашения конфиденциальной информации, NDA\n"
    "3. Недобросовестная конкуренция — сговор, демпинг, раздел рынков, картельные соглашения\n"
    "4. Воровство — кража, присвоение имущества, растрата, хищение\n"
    "5. Дискриминация и домогательства — сексуальные домогательства, дискриминация, травля\n"
    "6. Саботаж и вредительство — повреждение имущества, срыв проектов, подлог\n"
    "7. Угрозы и насилие — прямые или завуалированные угрозы, призывы к насилию\n\n"
    "Ответь ТОЛЬКО в формате JSON:\n"
    "{\n"
    '  "is_risky": true/false,\n'
    '  "risk_level": "none" | "low" | "medium" | "high",\n'
    '  "categories": ["список категорий"],\n'
    '  "details": [{"category": "...", "quote": "...", "description": "..."}],\n'
    '  "summary": "краткое резюме"\n'
    "}\n\n"
    "Если опасных тем нет: is_risky=false, risk_level=none, пустые списки.\n"
    "Отвечай строго по фактам транскрипции, без домыслов. Язык: русский."
)


class LLMAPI:
    """Обёртка над OpenAI-совместимым LLM API."""

    def __init__(self, api_url: str, model: str):
        self.api_url = api_url
        self.model = model

    @staticmethod
    def _extract_response_from_reasoning(text: str) -> str:
        """Извлекает фактический ответ из reasoning content, отсекая thinking process."""
        patterns = [
            "**Саммари встречи**",
            "Саммари встречи",
            "## Саммари встречи",
            "# Саммари встречи",
            "**Дата и время:**",
            "## Ключевые обсуждения",
            "## Задачи",
        ]
        for pattern in patterns:
            if pattern in text:
                idx = text.find(pattern)
                return text[idx:].strip()
        return text.strip()

    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.1, max_tokens: int = 1500) -> str:
        """Отправка запроса к LLM API."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.9,
        }
        resp = requests.post(f"{self.api_url}/chat/completions", json=payload)
        resp.raise_for_status()
        choice = resp.json()["choices"][0]["message"]
        result = choice.get("content", "").strip()
        if not result:
            reasoning = choice.get("reasoning_content", "").strip()
            result = self._extract_response_from_reasoning(reasoning)
        logger.debug("LLM chat response (first 200 chars): %s", result[:200])
        return result

    def summarize(self, transcript: str) -> str:
        """Суммаризация транскрипции."""
        result = self.chat(SUMMARIZE_PROMPT, transcript, temperature=0.1, max_tokens=1500)
        logger.info("LLM summarize response: %d chars", len(result))
        return result

    def check_risks(self, transcript: str) -> dict:
        """Выявление опасных обсуждений. Возвращает JSON-объект."""
        content = self.chat(RISK_PROMPT, transcript, temperature=0.0, max_tokens=1000)
        if "```" in content:
            content = content.split("```")[1].lstrip("json").strip()
        if not content:
            return {"is_risky": False, "risk_level": "none", "categories": [], "details": [], "summary": ""}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"is_risky": False, "risk_level": "none", "categories": [], "details": [], "summary": "Ошибка парсинга ответа LLM"}
