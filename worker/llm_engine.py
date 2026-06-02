"""LLM engine for summarization and risk detection."""

import json
import logging
import requests

logger = logging.getLogger(__name__)


SUMMARIZE_PROMPT = (
    "Ты — профессиональный ассистент для создания кратких протоколов встреч (саммари) на русском языке. "
    "Твоя задача — проанализировать предоставленную транскрипцию диалога и сформировать структурированное саммари, "
    "строго основываясь только на содержании разговора. Не добавляй никакой информации, которой нет в транскрипции. "
    "Не выдумывай факты.\n\n"
    "Требования к саммари:\n"
    "1. Заголовок: «Саммари встречи»\n"
    "2. Дата и время встречи: если в тексте упоминаются, укажи; иначе оставь поле «не указано».\n"
    "3. Участники: перечисли имена, должности или роли, которые упоминаются в разговоре. "
    "Если есть обращения по имени, выдели их. При отсутствии — «не определены».\n"
    "4. Тема встречи: одно-два предложения, о чём шла речь.\n"
    "5. Ключевые обсуждения и выводы: перечисли основные пункты обсуждения и достигнутые договорённости. "
    "Формат — маркированный список.\n"
    "6. Задачи (Action Items): таблица или список задач с указанием ответственного (если названо) "
    "и срока (если указан). Если задач нет — напиши «не обсуждались».\n"
    "7. Дополнительные заметки: любые другие важные упоминания.\n\n"
    "Стиль: деловой, лаконичный, русский язык.\n"
    "Ограничение: объём саммари не должен превышать 30% исходного текста.\n"
    "Игнорируй шум, повторы, несвязные фразы."
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
        return resp.json()["choices"][0]["message"]["content"].strip()

    def summarize(self, transcript: str) -> str:
        """Суммаризация транскрипции."""
        return self.chat(SUMMARIZE_PROMPT, transcript, temperature=0.1, max_tokens=1500)

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
