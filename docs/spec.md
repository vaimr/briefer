# Брифер — Бот для транскрибации и суммаризации встреч

## Описание

Matrix-бот, который принимает аудиосообщения и аудиофайлы из комнат Matrix, транскрибирует их с помощью Whisper, суммаризирует через LLM и возвращает в комнату PDF-файлы с полной транскрипцией и структурированным саммари встречи.

## Архитектура

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│  Matrix     │────▶│   bot    │────▶│   Redis     │
│  Homeserver │◀────│  (nio)   │     │   Queue     │
└─────────────┘     └──────────┘     └──────┬──────┘
                                            │
                                            ▼
                                     ┌─────────────┐
                                     │   worker    │
                                     │  (Whisper + │
                                     │   LLM +     │
                                     │  PDF gen)   │
                                     └──────┬──────┘
                                            │
                                            ▼
                                     ┌─────────────┐
                                     │  Matrix     │
                                     │  (results)  │
                                     └─────────────┘
```

### Компоненты

| Компонент | Назначение | Стек |
|-----------|-----------|------|
| **bot** | Приём аудио из Matrix, отправка в Redis-очередь, получение и отправка результатов | Python 3.11, matrix-nio, redis |
| **worker** | Транскрибация (Whisper), суммаризация (LLM), генерация PDF | Python 3.11, faster-whisper, requests, weasyprint, ffmpeg, pandoc |
| **Redis** | Очередь задач (`transcription_queue`) и канал результатов (`task_results`) | Redis 7 |
| **LLM** | Суммаризация транскрипции | llama.cpp API (OpenAI-compatible), модель qwen3.6-a3b-mtp:35b |

## Структура проекта

```
.
├── bot/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── bot.py
├── worker/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── worker.py
├── data/                # общий том для временных файлов
├── docs/
│   └── spec.md          # этот файл
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## docker-compose.yml

```yaml
version: "3.8"

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    volumes:
      - redis_data:/data

  bot:
    build: ./bot
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy
    environment:
      - MATRIX_HOMESERVER=${MATRIX_HOMESERVER}
      - MATRIX_USER=${MATRIX_USER}
      - MATRIX_PASSWORD=${MATRIX_PASSWORD}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    volumes:
      - ./data:/data

  worker:
    build: ./worker
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - LLM_API_URL=http://faex:8080/v1
      - LLM_MODEL_NAME=qwen3.6-a3b-mtp:35b
      - WHISPER_MODEL=large-v3
      - DATA_DIR=/data
      - TZ=Europe/Moscow
    volumes:
      - ./data:/data
      - whisper_cache:/root/.cache/huggingface
    extra_hosts:
      - "faex:host-gateway"

volumes:
  redis_data:
  whisper_cache:
```

## Переменные окружения

Файл `.env`:

```ini
MATRIX_HOMESERVER=https://matrix.example.com
MATRIX_USER=@transcriber_bot:example.com
MATRIX_PASSWORD=your_password
# MATRIX_ACCESS_TOKEN=...   # можно использовать токен вместо пароля
```

## Логика работы

### Bot (bot/bot.py)

1. Подключение к Matrix Homeserver по токену или логин по паролю
2. Подписка на события `RoomMessageAudio` и `RoomMessageFile` (audio/*)
3. При получении аудио:
   - Скачивание файла через Matrix Client Media API
   - Сохранение в `/data/input/{message_id}.{extension}`
   - Отправка задачи в Redis-очередь: `room_id|audio_path`
   - Ответ пользователю: «Файл принят, идёт обработка...»
4. Подписка на Redis pub/sub канал `task_results`
5. При получении результата — загрузка PDF-файлов и отправка в комнату как `m.file`

### Worker (worker/worker.py)

1. Бесконечный цикл: `blpop("transcription_queue")`
2. Для каждой задачи:
   - **Конвертация аудио**: ffmpeg → WAV 16kHz mono
   - **Транскрибация**: faster-whisper (large-v3), VAD filter, beam_size=5
   - **Суммаризация**: LLM API (llama.cpp), системный промпт для структурированного саммари
   - **Генерация PDF**: Markdown → PDF через pandoc + weasyprint
   - **Отправка результата**: publish в Redis `task_results`
3. Очистка временных файлов

## Инфраструктура

### Health Check
Каждый сервис (bot, worker) предоставляет `/health` endpoint для Kubernetes readiness/liveness probes:
- **GET /health** — возвращает `200 OK` если сервис работает, `503` если есть проблемы
- Проверяет: подключение к Redis, доступность LLM API (для worker), подключение к Matrix (для bot)
- Ответ: `{"status": "ok", "checks": {"redis": "ok", "llm": "ok", "matrix": "ok"}}`

### Метрики
Каждый сервис предоставляет `/prometheus` endpoint в формате Prometheus:
- **GET /prometheus** — возвращает метрики в формате `text/plain; version=0.0.4`
- Метрики: количество обработанных задач, время обработки, ошибки, глубина очереди
- Библиотека: `prometheus-client`

### Логирование
- **Строго STDOUT** — никаких локальных файлов логов
- Формат: JSON (structured logging) для лёгкого парсинга в k8s
- Уровни: INFO, WARNING, ERROR
- Каждый лог содержит: timestamp, level, service, task_id (если есть), message

## Системный промпт суммаризации

```
Ты — профессиональный ассистент для создания кратких протоколов встреч (саммари) на русском языке. Твоя задача — проанализировать предоставленную транскрипцию диалога и сформировать структурированное саммари, строго основываясь только на содержании разговора. Не добавляй никакой информации, которой нет в транскрипции. Не выдумывай факты.

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
Игнорируй шум, повторы, несвязные фразы.
```

## Системный промпт выявления опасных обсуждений

Отдельный запрос к LLM. Запускается параллельно с суммаризацией.

```
Ты — система безопасности, анализирующая транскрипции деловых встреч на наличие опасных тем.

Задача: проанализировать транскрипцию и выявить упоминания следующих категорий контента:

1. **Нарушение закона** — обсуждение действий, нарушающих УК, КоАП, ФЗ (мошенничество, коррупция, уклонение от налогов, незаконная деятельность)
2. **Коммерческая тайна** — обсуждение разглашения конфиденциальной информации, секретных данных, NDA
3. **Недобросовестная конкуренция** — сговор, демпинг, раздел рынков, бойкот, картельные соглашения
4. **Воровство** — кража, присвоение имущества, растрата, хищение
5. **Дискриминация и домогательства** — сексуальные домогательства, дискриминация по любому признаку, травля
6. **Саботаж и вредительство** — намеренное повреждение имущества, срыв проектов, подлог
7. **Угрозы и насилие** — прямые или завуалированные угрозы, призывы к насилию

Требования к ответу:
- Формат JSON:
  ```json
  {
    "is_risky": true/false,
    "risk_level": "none" | "low" | "medium" | "high",
    "categories": ["список нарушенных категорий"],
    "details": [
      {
        "category": "категория",
        "timestamp": "если есть время/контекст",
        "quote": "цитата из транскрипции",
        "participants": ["участники"],
        "description": "краткое описание"
      }
    ],
    "summary": "краткое резюме выявленных рисков"
  }
  ```
- Если опасных тем нет: `is_risky: false`, `risk_level: "none"`, пустые `categories` и `details`
- Отвечай строго по фактам транскрипции, без домыслов
- Язык ответов: русский

Стиль: объективный, фактологический.
```

## Инструкция по запуску

1. Создать файл `.env` с переменными Matrix-окружения
2. Убедиться, что LLM-сервер `faex` доступен с хост-машины
3. Собрать образы: `docker compose build`
4. Запустить: `docker compose up -d`
5. Бот автоматически войдёт в Matrix и начнёт принимать аудио

## Зависимости

### bot/requirements.txt
- matrix-nio>=0.24.0
- redis

### worker/requirements.txt
- faster-whisper>=1.0.0
- redis
- requests
- weasyprint

### worker Dockerfile
- ffmpeg
- pandoc
- texlive-latex-recommended
- texlive-latex-extra
- texlive-fonts-recommended
- lmodern

## Планы развития

- [ ] Поддержка разных форматов аудио (m4a, ogg, webm)
- [ ] Распознавание спикеров (speaker diarization)
- [ ] Конфигурация через Matrix state events / m.room.account_data
- [ ] Health-check и мониторинг очереди
- [ ] Логирование (structured logging)
- [ ] Обработка ошибок с уведомлением пользователя
- [ ] Поддержка нескольких воркеров (горизонтальное масштабирование)
- [ ] Кэширование результатов по хэшу аудио
- [ ] Webhook-уведомления о готовности
- [ ] Поддержка Telegram как альтернативного канала
