# Briefer — Matrix Bot для расшифровки и саммари аудио

AI-бот для Matrix, который принимает аудио сообщения (голосовые, аудиофайлы), транскрибирует их с помощью OpenAI Whisper, генерирует саммари через LLM (OpenAI-compatible API), и возвращает результаты в виде Markdown + PDF файлов прямо в комнату.

## Архитектура

```
┌──────────┐     аудио       ┌───────┐     очередь      ┌────────┐
│  Matrix  │ ──────────────► │  Bot  │ ──────────────► │        │
│  Room    │   (audio/file)  │ (async)│   Redis RPUSH   │        │
└──────────┘                 └───────┘                  │        │
         ▲                   │  ▲                      │  Redis │
         │                   │  │                      │        │
         │  результаты       │  │ blpop                │  Queue │
         │  (MD+PDF)         │  │                      │        │
         │                   ▼  │                      └────────┘
         │              ┌───────┐
         │              │Worker │
         │              │(sync) │
         │              └───────┘
         │                 │
         │       ┌─────────┴─────────┐
         │       ▼                   ▼
         │  ┌─────────┐      ┌──────────┐
         │  │ Whisper │      │   LLM    │
         │  │ (local) │      │ (API)    │
         │  └─────────┘      └──────────┘
         │       │                   │
         │       └─────────┬─────────┘
         │                 ▼
         │         MD + PDF файлы
         │                 │
         └─────────────────┘
              Redis PUB/SUB
              (task_results)
```

### Компоненты

| Компонент    | Описание                                                                 | Порт  |
|-------------|--------------------------------------------------------------------------|-------|
| **Bot**     | Matrix-клиент (nio). Слушает аудио/файлы, скачивает, пушит в Redis, получает результаты через pub/sub | 8081  |
| **Worker**  | Pull-воркер из Redis. Транскрибация → LLM саммари + риск-анализ → PDF → pub/sub результатов | 8082  |
| **Redis**   | Очередь (`transcription_queue`) + pub/sub каналы (`task_results`, `task_errors`, `task_cleanup`) | 6379  |
| **LLM API** | OpenAI-compatible endpoint (например, vLLM/Faex) для саммари и риск-анализа | —     |

### Pipeline обработки

```
1. Пользователь → отправляет аудио в Matrix
2. Bot → скачивает файл, пушит в Redis: "room_id|audio_path|filename|event_id"
3. Worker → blpop из очереди
4. Worker → Whisper транскрибация → текст + длительность
5. Worker → параллельно: LLM саммари + LLM риск-анализ
6. Worker → генерация PDF (transcript + summary + risk_alert при необходимости)
7. Worker → Redis publish "task_results" с путями к файлам
8. Bot → pub/sub → скачивает файлы → загружает в Matrix как m.file
9. Bot → Redis publish "task_cleanup" → Worker удаляет временные файлы
```

### Каналы Redis

| Канал               | Направление    | Описание                          |
|---------------------|----------------|-----------------------------------|
| `transcription_queue` | Bot → Worker   | LPUSH от бота, BLPOP от воркера |
| `task_results`      | Worker → Bot   | Pub/Sub с JSON результатами      |
| `task_errors`       | Worker → Bot   | Pub/Sub с ошибками               |
| `task_cleanup`      | Bot → Worker   | Pub/Sub с task_id для очистки    |

### Формат очереди

```
room_id|/data/input/<hash>.<ext>|<original_filename>|<event_id>
```

### Формат результата (task_results)

```json
{
  "task_id": "abc123...",
  "room_id": "!xyz:server",
  "original_filename": "meeting.ogg",
  "event_id": "$abc...",
  "transcript_md": "/tmp/results/abc/transcript.md",
  "transcript_pdf": "/tmp/results/abc/transcript.pdf",
  "summary_md": "/tmp/results/abc/summary.md",
  "summary_pdf": "/tmp/results/abc/summary.pdf",
  "risk_files": ["/tmp/results/abc/risk_alert.pdf"],
  "timestamp": "2025-01-15T10:30:00"
}
```

## Быстрое развертывание

### Требования

- Docker + Docker Compose
- Matrix homeserver с правами на создание бот-аккаунта
- LLM API (OpenAI-compatible, например vLLM)
- GPU (опционально, для Whisper large-v3)

### 1. Клонировать и настроить

```bash
git clone <repo>
cd briefer
cp .env.example .env
```

### 2. Заполнить `.env`

```bash
MATRIX_HOMESERVER=https://matrix.example.com
MATRIX_USER=@briefer_bot:example.com
MATRIX_PASSWORD=your_bot_password
```

### 3. Запустить

```bash
docker compose up -d --build
```

### 4. Проверить

```bash
# Health endpoints
curl http://localhost:8081/health   # bot
curl http://localhost:8082/health   # worker

# Logs
docker compose logs -f bot worker
```

## Настройки (`.env`)

Все переменные окружения задаются в `.env` (скопируйте `.env.example`).

### Matrix-аутентификация

Бот подключается к Matrix для прослушивания сообщений. **Приоритет: `MATRIX_ACCESS_TOKEN` > `MATRIX_PASSWORD`**.

| Переменная              | По умолчанию       | Обязательно | Описание                          |
|------------------------|--------------------|-------------|-----------------------------------|
| `MATRIX_HOMESERVER`    | *(required)*       | ✅ да       | URL Matrix homeserver (`https://...`) |
| `MATRIX_USER`          | *(required)*       | ✅ да       | Bot аккаунт (с `@`, напр. `@bot:server.com`) |
| `MATRIX_ACCESS_TOKEN`  |                    | 🔑 да¹      | **Приоритет:** токен аутентификации |
| `MATRIX_PASSWORD`      |                    | ✅ да²      | Пароль (используется если токен не задан) |

> ¹ Если задан `MATRIX_ACCESS_TOKEN` — пароль игнорируется.
> ² Если не задан ни токен, ни пароль — бот не запустится.

### Redis

| Переменная              | По умолчанию | Описание                          |
|------------------------|--------------|-----------------------------------|
| `REDIS_HOST`           | `redis`      | Host Redis-сервера                |
| `REDIS_PORT`           | `6379`       | Порт Redis                        |

### LLM (Worker)

Worker общается с LLM через **OpenAI-compatible `/chat/completions`** API (vLLM, Ollama, OpenAI, Anthropic-proxy и т.д.).

| Переменная              | По умолчанию              | Обязательно | Описание                          |
|------------------------|---------------------------|-------------|-----------------------------------|
| `WORKER_LLM_API_URL`   | `http://faex:8080/v1`     | ✅ да       | Базовый URL LLM API               |
| `WORKER_LLM_MODEL_NAME`| `qwen3.6-a3b-mtp:35b`     | ✅ да       | Имя модели для запросов           |

#### Примеры LLM-бэкендов

```bash
# vLLM (локальный)
WORKER_LLM_API_URL=http://vllm-host:8000/v1
WORKER_LLM_MODEL_NAME=your-model-name

# Ollama (локальный)
WORKER_LLM_API_URL=http://localhost:11434/v1
WORKER_LLM_MODEL_NAME=qwen3:8b

# OpenAI (облако)
WORKER_LLM_API_URL=https://api.openai.com/v1
WORKER_LLM_MODEL_NAME=gpt-4o

# Anthropic (через OpenAI-совместимый прокси)
WORKER_LLM_API_URL=https://your-proxy/v1
WORKER_LLM_MODEL_NAME=claude-sonnet-4-20250514
```

#### Параметры запроса к LLM

| Параметр      | Значение  | Описание                          |
|--------------|-----------|-----------------------------------|
| `temperature`| `0.1`     | Для саммари, `0.0` для риск-анализа |
| `top_p`      | `0.9`     | Nucleus sampling                  |
| `timeout`    | `60s`     | Таймаут HTTP-запроса              |
| `max_retries`| `3`       | Повторные попытки при 5xx/timeout |
| `retry_delay`| `2s`      | Задержка между повторами          |

#### Поддержка reasoning models

Worker поддерживает модели с reasoning (Qwen3.6-MTP и аналоги). Если в ответе есть `reasoning_content`, финальный ответ извлекается из него (ищет последнее вхождение `## Саммари встречи` или `# Саммари встречи`).

#### Ограничения

- Транскрипция обрезается до **4000 символов** перед отправкой в LLM
- Саммари обрезается до **2000 символов**
- Для риск-анализа ответ ожидается в JSON-формате (парсится автоматически, поддержка fenced code blocks ` ```json `)

#### docker-compose: резолв LLM-хоста

Если LLM на отдельном хосте, добавьте в `docker-compose.yml`:

```yaml
worker:
  extra_hosts:
    - "faex:192.168.0.104"  # резолв хоста LLM
```

### Worker

| Переменная              | По умолчанию              | Описание                          |
|------------------------|---------------------------|-----------------------------------|
| `WORKER_WHISPER_MODEL` | `large-v3`                | Whisper модель (tiny/base/small/medium/large-v3) |
| `WORKER_DATA_DIR`      | `/data`                   | Директория для входных аудио      |
| `WORKER_HEALTH_PORT`   | `8082`                    | Порт /health + metrics            |
| `LOG_LEVEL`            | `INFO`                    | Уровень логирования               |
| `MAX_TASK_DURATION`    | `900`                     | Макс. длительность задачи (сек)   |
| `MAX_RETRIES`          | `3`                       | Макс. ретраев при ошибке          |

### Bot

| Переменная              | По умолчанию       | Описание                          |
|------------------------|--------------------|-----------------------------------|
| `LOG_LEVEL`            | `INFO`             | Уровень логирования               |
| `HEALTH_PORT`          | `8081`             | Порт /health + metrics            |
| `HELP_TEXT_FILE`       | `/etc/briefer/help.txt` | Путь к файлу help-сообщения |
| `TZ`                   | `Europe/Moscow`    | Часовой                           |

## Тесты

```bash
# Все тесты
make test

# Без покрытия
make test-no-cov

# Линтинг
make lint

# Форматирование
make format
```

## Мониторинг

### Prometheus Metrics

| Metric                        | Тип      | Описание                          |
|-------------------------------|----------|-----------------------------------|
| `bot_messages_received`       | Counter  | Входящие сообщения (audio/other)  |
| `bot_messages_processed`      | Counter  | Обработанные сообщения            |
| `bot_queue_depth`             | Gauge    | Глубина очереди                   |
| `worker_tasks_processed`      | Counter  | Обработанные задачи (success/error)|
| `worker_processing_duration`  | Histogram| Длительность обработки            |
| `worker_whisper_loaded`       | Gauge    | 1 = Whisper загружен              |

### Health Checks

- Bot: `GET http://<bot-host>:8081/health`
- Worker: `GET http://<worker-host>:8082/health`

## Структура проекта

```
briefer/
├── bot/                          # Matrix bot
│   ├── __main__.py               # Entry point, sync loop
│   ├── config.py                 # BotConfig (pydantic-settings)
│   ├── matrix_client.py          # Matrix client wrapper
│   ├── result_listener.py        # Pub/sub results consumer
│   ├── audio_downloader.py       # Audio download helpers
│   ├── health.py                 # HTTP health server
│   ├── metrics.py                # Prometheus metrics (bot)
│   ├── notifications.py          # Error notifications
│   ├── pdf_uploader.py           # PDF upload to Matrix
│   └── Dockerfile
├── worker/                       # Processing worker
│   ├── __main__.py               # Entry point, queue loop
│   ├── config.py                 # WorkerConfig (pydantic-settings)
│   ├── whisper_engine.py         # OpenAI Whisper transcription
│   ├── llm_engine.py             # LLM API client
│   ├── llm_client.py             # Summarize + risk check
│   ├── pipeline.py               # Processing pipeline
│   ├── pdf_generator.py          # Markdown → PDF
│   ├── chunking.py               # Transcript chunking
│   ├── retry.py                  # Retry logic
│   ├── dlq.py                    # Dead letter queue
│   ├── task_tracker.py           # Task lifecycle tracking
│   ├── graceful_shutdown.py      # Graceful shutdown
│   ├── audio_converter.py        # Audio format conversion
│   ├── audio.py                  # Audio utilities
│   ├── health.py                 # HTTP health server
│   ├── metrics.py                # Prometheus metrics (worker)
│   └── Dockerfile
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests (~50+ файлов)
│   └── integration/              # Integration tests
├── docker-compose.yml            # Orchestration
├── Makefile                      # Dev commands
├── .env.example                  # Environment template
└── docs/                         # Design docs
```

## Лимиты и ограничения

- Аудио файлы скачиваются в `/data/input/` (volume mount)
- Результаты пишутся в `/tmp/results/<task_id>/` (volume mount `results`)
- Worker удаляет результаты после публикации cleanup в Redis
- Whisper модель кэшируется в `/root/.cache/huggingface` (volume `whisper_cache`)
- Redis данные в `redis_data` volume
