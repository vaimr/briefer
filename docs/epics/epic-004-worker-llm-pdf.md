# EPIC-004: Worker — LLM Summarization & PDF Generation

## Описание

Воркер получает транскрипцию из T3.3, суммаризирует через LLM API (llama.cpp, OpenAI-compatible), генерирует Markdown-шаблоны и конвертирует в PDF через pandoc + weasyprint.

**Зависимости:** EPIC-003 (Worker — Audio Processing)

**Цель приёмки эпика:**
- LLM API получает транскрипцию и возвращает структурированное саммари
- Обработка ошибок LLM API с retry (exponential backoff)
- Длинная транскрипция (> 4000 tokens) разбивается на чанки
- Markdown-шаблоны генерируются для транскрипции и саммари
- PDF генерируется корректно с поддержкой кириллицы
- Два PDF-файла: transcript.pdf и summary.pdf

---

## T4.1: LLM API integration with retry

**Длительность:** ~1.5 часа  
**Зависимости:** T1.4 (Config)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Транскрипция (текст) | POST к LLM API с системным промптом, retry с backoff | Суммаризация (текст) |

### Критерии приёмки
- [ ] `worker/llm.py` — функция `summarize(transcript: str, config: WorkerConfig) -> str`
- [ ] Системный промпт из spec.md (протокол встречи)
- [ ] POST `/{llm_api_url}/chat/completions` с payload: model, messages, temperature=0.1, max_tokens=1500, top_p=0.9
- [ ] Retry: до 3 попыток с exponential backoff (1s, 2s, 4s)
- [ ] Обработка HTTPError → raise с кодом статуса
- [ ] Обработка ConnectionError → retry
- [ ] Обработка 429 (rate limit) → retry с увеличенным backoff (5s, 10s, 20s)
- [ ] Обработка 5xx → retry

### Граничные случаи
- LLM API недоступен → 3 retry → raise ConnectionError
- LLM возвращает 429 → retry с увеличенным backoff
- LLM возвращает 500 → retry с обычным backoff
- LLM возвращает пустой response → ValueError
- LLM возвращает response без choices → ValueError
- Транскрипция > max_tokens → чанкинг (T4.2)
- Response JSON parse error → ValueError

### Пошаговый план
1. Создать `worker/llm.py`:
   ```python
   import logging
   import time
   import requests
   from worker.config import WorkerConfig
   
   logger = logging.getLogger(__name__)
   
   SYSTEM_PROMPT = """Ты — профессиональный ассистент для создания кратких протоколов встреч (саммари) на русском языке. Твоя задача — проанализировать предоставленную транскрипцию диалога и сформировать структурированное саммари, строго основываясь только на содержании разговора. Не добавляй никакой информации, которой нет в транскрипции. Не выдумывай факты.

Требования к саммари:
1. Заголовок: «Саммари встречи»
2. Дата и время встречи: если в тексте упоминаются, укажи; иначе оставь поле «не указано».
3. Участники: перечисли имена, должности или роли, которые упоминаются в разговоре. Если есть обращения по имени, выдели их. При отсутствии — «не определены».
4. Тема встречи: одно-два предложения, о чём шла речь.
5. Ключевые обсуждения и выводы: перечисли основные пункты обсуждения и достигнутые договорённости. Формат — маркированный список.
6. Задачи (Action Items): таблица или список задач с указанием ответственного (если названо) и срока (если указан). Если задач нет — напиши «не обсуждались».
7. Дополнительные заметки: любые другие важные упоминания.

Стиль: деловой, лаконичный, русский язык.
Ограничение: объём саммари не должен превышать 30% исходного текста.
Игнорируй шум, повторы, несвязные фразы."""

   MAX_RETRIES = 3
   BASE_BACKOFF = 1  # seconds
   RATE_LIMIT_BACKOFF = 5  # seconds for 429

   def summarize(transcript: str, config: WorkerConfig) -> str:
       payload = {
           "model": config.llm_model_name,
           "messages": [
               {"role": "system", "content": SYSTEM_PROMPT},
               {"role": "user", "content": transcript}
           ],
           "temperature": 0.1,
           "max_tokens": 1500,
           "top_p": 0.9
       }
       
       last_error = None
       for attempt in range(MAX_RETRIES):
           try:
               response = requests.post(
                   f"{config.llm_api_url}/chat/completions",
                   json=payload,
                   timeout=120
               )
               
               if response.status_code == 429:
                   backoff = RATE_LIMIT_BACKOFF * (2 ** attempt)
                   logger.warning("Rate limited (429). Retrying in %ds...", backoff)
                   time.sleep(backoff)
                   continue
               
               response.raise_for_status()
               choices = response.json().get("choices")
               if not choices:
                   raise ValueError("LLM response has no choices")
               
               content = choices[0]["message"]["content"].strip()
               if not content:
                   raise ValueError("LLM response content is empty")
               
               logger.info("LLM summarization complete: %d chars", len(content))
               return content
               
           except requests.exceptions.ConnectionError as e:
               last_error = e
               backoff = BASE_BACKOFF * (2 ** attempt)
               logger.warning("Connection error. Retry %d/%d in %ds...", attempt + 1, MAX_RETRIES, backoff)
               time.sleep(backoff)
           except requests.exceptions.HTTPError as e:
               if response.status_code >= 500:
                   last_error = e
                   backoff = BASE_BACKOFF * (2 ** attempt)
                   logger.warning("Server error (%d). Retry %d/%d in %ds...",
                                response.status_code, attempt + 1, MAX_RETRIES, backoff)
                   time.sleep(backoff)
               else:
                   raise
       
       raise RuntimeError(f"LLM summarization failed after {MAX_RETRIES} retries: {last_error}")
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_llm.py`:
  - `test_summarize_returns_string()` — мокает requests.post, проверяет что возвращается string
  - `test_summarize_posts_correct_payload()` — проверяет что POST с правильным JSON
  - `test_summarize_retries_on_429()` — 429 → retry с увеличенным backoff
  - `test_summarize_retries_on_500()` — 500 → retry с обычным backoff
  - `test_summarize_retries_on_connection_error()` — ConnectionError → retry
  - `test_summarize_raises_after_max_retries()` — 3 failure → RuntimeError
  - `test_summarize_empty_choices_raises()` — response без choices → ValueError
  - `test_summarize_empty_content_raises()` — content = "" → ValueError
  - `test_summarize_success_on_first_try()` — 200 OK → без retry
  - `test_summarize_400_raises_immediately()` — 400 → raise без retry

---

## T4.2: Chunking for long transcripts

**Длительность:** ~1 час  
**Зависимости:** T4.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Транскрипция > 4000 символов | Разбиение на чанки по ~3000 символов, LLM для каждого, объединение | Полная суммаризация |

### Критерии приёмки
- [ ] `worker/chunking.py` — функции `chunk_text(text: str, chunk_size: int = 3000) -> list[str]` и `merge_summaries(summaries: list[str]) -> str`
- [ ] Chunking: разбивает текст по предложениям (не посередине предложения)
- [ ] Максимальный размер чанка: chunk_size символов
- [ ] Минимальный размер чанка: 200 символов (не создавать микро-чанки)
- [ ] Merge: объединяет суммаризации чанков в единый текст
- [ ] Если текст ≤ chunk_size → один чанк, без разделения

### Граничные случаи
- Текст = 0 символов → пустой список
- Текст = 100 символов → один чанк
- Текст = 10000 символов → ~4 чанка
- Текст заканчивается посередине слова → разбивка по последнему пробелу
- Все чанки вернули пустое саммари → вернуть "Не удалось создать саммари"

### Пошаговый план
1. Создать `worker/chunking.py`:
   ```python
   import re
   
   def chunk_text(text: str, chunk_size: int = 3000) -> list[str]:
       if len(text) <= chunk_size:
           return [text] if text.strip() else []
       
       chunks = []
       current = ""
       
       # Разбиваем по предложениям
       sentences = re.split(r'(?<=[.!?])\s+', text)
       
       for sentence in sentences:
           if len(current) + len(sentence) > chunk_size and current:
               chunks.append(current.strip())
               current = sentence
           else:
               current += " " + sentence if current else sentence
       
       if current.strip():
           chunks.append(current.strip())
       
       # Фильтруем микро-чанки
       return [c for c in chunks if len(c) >= 200]
   
   def merge_summaries(summaries: list[str]) -> str:
       if not summaries:
           return "Не удалось создать саммари"
       if len(summaries) == 1:
           return summaries[0]
       
       # Простое объединение: заголовок + все саммари
       return "\n\n---\n\n".join(summaries)
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_chunking.py`:
  - `test_chunk_text_short_text_single_chunk()` — 100 символов → 1 чанк
  - `test_chunk_text_long_text_multiple_chunks()` — 10000 символов → >1 чанк
  - `test_chunk_text_no_mid_sentence_break()` — не разбивает посередине предложения
  - `test_chunk_text_empty_text()` — "" → пустой список
  - `test_chunk_text_min_chunk_size()` — микро-чанки < 200 символов → фильтруются
  - `test_merge_summaries_single()` — 1 summary → возвращает как есть
  - `test_merge_summaries_multiple()` — 3 summaries → объединены с "---"
  - `test_merge_summaries_empty()` — [] → "Не удалось создать саммари"

---

## T4.3: Markdown template generation

**Длительность:** ~1 час  
**Зависимости:** нет

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Транскрипция + саммари + метаданные | Генерация Markdown-шаблонов | Два Markdown-строки: transcript_md и summary_md |

### Критерии приёмки
- [ ] `worker/templates.py` — функция `generate_markdown(transcript, segments, summary, duration, date_str) -> tuple[str, str]`
- [ ] Transcript MD: заголовок "Полная транскрипция", дата, длительность, текст
- [ ] Summary MD: заголовок "Саммари встречи", саммари
- [ ] Поддержка кириллицы в Markdown (UTF-8)
- [ ] Segments → форматированный список с таймкодами

### Граничные случаи
- segments = [] → транскрипция без спикеров
- duration = 0 → "0 сек"
- summary = "Не удалось создать саммари" → показывать как есть
- transcript = "" → пустая транскрипция

### Пошаговый план
1. Создать `worker/templates.py`:
   ```python
   from datetime import datetime
   
   def generate_markdown(transcript: str, segments: list[dict], summary: str,
                         duration: float, date_str: str | None = None) -> tuple[str, str]:
       if date_str is None:
           date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
       
       # Transcript markdown
       transcript_md = f"# Полная транскрипция\n\n"
       transcript_md += f"**Дата:** {date_str}\n"
       transcript_md += f"**Длительность:** {duration:.0f} сек\n\n"
       
       if segments:
           transcript_md += "## Сегменты\n\n"
           for seg in segments:
               start = f"{seg['start']:.1f}s"
               end = f"{seg['end']:.1f}s"
               transcript_md += f"- **{start} → {end}** Speaker {seg['speaker']}: {seg['text']}\n"
       else:
           transcript_md += f"{transcript}\n"
       
       # Summary markdown
       summary_md = f"# Саммари встречи\n\n"
       summary_md += f"**Дата:** {date_str}\n\n"
       summary_md += f"{summary}\n"
       
       return transcript_md, summary_md
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_templates.py`:
  - `test_generate_markdown_returns_two_strings()` — проверяет тип возврата
  - `test_transcript_md_has_header()` — содержит "# Полная транскрипция"
  - `test_transcript_md_has_date()` — содержит "**Дата:**"
  - `test_transcript_md_has_duration()` — содержит "**Длительность:**"
  - `test_transcript_md_has_segments()` — segments → список с таймкодами
  - `test_summary_md_has_header()` — содержит "# Саммари встречи"
  - `test_summary_md_contains_summary_text()` — summary вставлен
  - `test_date_str_default()` — без date_str → текущая дата

---

## T4.4: PDF generation with Cyrillic support

**Длительность:** ~2 часа  
**Зависимости:** T4.3, T1.2 (Docker с pandoc + texlive)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Markdown-строка + output path | pandoc → PDF через weasyprint, кириллица | PDF-файл на диске |

### Критерии приёмки
- [ ] `worker/pdf.py` — функция `generate_pdf(markdown_content: str, output_path: str) -> str`
- [ ] Записывает Markdown во временный `.md` файл
- [ ] Вызывает `pandoc md_path -o pdf_path --pdf-engine=weasyprint`
- [ ] Поддержка кириллицы: латинский шрифт + шрифт с кириллицей
- [ ] Удаляет временный `.md` файл после генерации PDF
- [ ] Возвращает путь к PDF

### Граничные случаи
- Markdown пустой → пустой PDF (или ошибка)
- Markdown > 100KB → warning
- pandoc не установлен → FileNotFoundError
- weasyprint не установлен → PDF не создан
- PDF не создан после pandoc → FileNotFoundError
- Ошибка кодировки UTF-8 → UnicodeEncodeError

### Пошаговый план
1. Обновить `worker/Dockerfile` — добавить шрифт с кириллицей:
   ```dockerfile
   RUN apt-get install -y --no-install-recommends fonts-liberation
   ```
2. Создать `worker/pdf.py`:
   ```python
   import os
   import subprocess
   import logging
   from pathlib import Path
   
   logger = logging.getLogger(__name__)
   
   def generate_pdf(markdown_content: str, output_path: str) -> str:
       md_path = output_path.rsplit(".", 1)[0] + ".md"
       
       # Записываем Markdown
       Path(md_path).write_text(markdown_content, encoding="utf-8")
       
       if len(markdown_content) > 100_000:
           logger.warning("Large markdown file: %d bytes", len(markdown_content))
       
       # Генерируем PDF
       try:
           subprocess.run(
               ["pandoc", md_path, "-o", output_path, "--pdf-engine=weasyprint"],
               check=True, capture_output=True, text=True
           )
       except subprocess.CalledProcessError as e:
           logger.error("pandoc failed: %s", e.stderr)
           raise RuntimeError(f"PDF generation failed: {e.stderr}") from e
       except FileNotFoundError:
           raise FileNotFoundError("pandoc not found. Install pandoc and weasyprint.")
       
       if not os.path.exists(output_path):
           raise FileNotFoundError(f"PDF file not created: {output_path}")
       
       # Удаляем временный .md
       os.remove(md_path)
       
       logger.info("PDF generated: %s (%d bytes)", output_path, os.path.getsize(output_path))
       return output_path
   ```
3. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_pdf.py`:
  - `test_generate_pdf_creates_pdf_file()` — мокает subprocess, проверяет что PDF создан
  - `test_generate_pdf_writes_md_temporarily()` — .md файл создаётся и удаляется
  - `test_generate_pdf_cyrillic_content()` — кириллический текст → UTF-8 кодировка
  - `test_generate_pdf_pandoc_error_raises()` — CalledProcessError → RuntimeError
  - `test_generate_pdf_pandoc_not_found_raises()` — FileNotFoundError
  - `test_generate_pdf_pdf_not_created_raises()` — subprocess прошёл но PDF не создан → FileNotFoundError
  - `test_generate_pdf_large_content_warns()` — > 100KB → warning в логе

---

## Интеграционный тест

### `tests/integration/test_worker_llm_pdf.py`
- `test_summarize_and_generate_pdf()` — транскрипция → LLM → Markdown → PDF → PDF существует
- `test_pdf_contains_cyrillic()` — PDF содержит кириллический текст
