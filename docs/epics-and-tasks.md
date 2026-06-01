# Брифер — Сводная таблица эпики, задач и подзадач

> Эта таблица — навигационный индекс. Каждая строка ведёт на детальный файл, где каждая задача декомпозирована на атомарные подзадачи с TDD-требованиями, критериями приёмки и пошаговыми планами.

## Зависимости между эпиками

```
EPIC-001 (Foundation)
    │
    ├─▶ EPIC-002 (Bot — Matrix Integration) ──┐
    │                                           │
    ├─▶ EPIC-003 (Worker — Audio Pipeline) ───┤
    │                                           │
    │                                           ▼
    │                                    EPIC-005 (Bot — Result Delivery)
    │                                           ▲
    ├─▶ EPIC-004 (Worker — LLM + PDF) ────────┤
    │                                           │
    └───────────────────────────────────────────┘
    │
    └─▶ EPIC-006 (Reliability) ──┐
    │                             │
    └─▶ EPIC-007 (Observability) ─┘
```

Все эпики Фазы 1 (001–005) можно параллелить после Foundation. Фазы 2 (006–007) — после 005.

## Эпики

| № | Название | Эпик файл | Задачи | Подзадач | Статус |
|---|----------|-----------|--------|----------|--------|
| **001** | Foundation — Инфраструктура проекта | [epic-001](epics/epic-001-project-foundation.md) | 5 | 15 | ✅ |
| **002** | Bot — Matrix Integration & Audio Ingestion | [epic-002](epics/epic-002-bot-matrix-audio.md) | 5 | 10 | ⬜ |
| **003** | Worker — Audio Processing & Transcription | [epic-003](epics/epic-003-worker-audio-transcription.md) | 4 | 8 | ⬜ |
| **004** | Worker — LLM Summarization & PDF Generation | [epic-004](epics/epic-004-worker-llm-pdf.md) | 4 | 8 | ⬜ |
| **005** | Bot — Result Delivery | [epic-005](epics/epic-005-bot-result-delivery.md) | 4 | 6 | ⬜ |
| **006** | Reliability & Error Handling | [epic-006](epics/epic-006-reliability-errors.md) | 4 | 4 | ⬜ |
| **007** | Observability & Configuration | [epic-007](epics/epic-007-observability-config.md) | 3 | 3 | ⬜ |

**Итого:** 7 эпики, 29 задач, 54 подзадачи

---

## EPIC-001: Foundation — Инфраструктура проекта

### T1.1: Directory Structure

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 1.1.1 | Создать структуру директорий проекта | [T1.1.1](subtasks/epic-001/T1.1.1-create-directory-structure.md) | — |
| 1.1.2 | Создать __init__.py и package файлы | [T1.1.2](subtasks/epic-001/T1.1.2-create-init-files.md) | 1.1.1 |
| 1.1.3 | Создать .gitignore | [T1.1.3](subtasks/epic-001/T1.1.3-create-gitignore.md) | 1.1.1 |

### T1.2: Docker Container Infrastructure

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 1.2.1 | Создать Bot Dockerfile | [T1.2.1](subtasks/epic-001/T1.2.1-bot-dockerfile.md) | 1.1.1 |
| 1.2.2 | Создать Worker Dockerfile | [T1.2.2](subtasks/epic-001/T1.2.2-worker-dockerfile.md) | 1.1.1 |
| 1.2.3 | Валидация docker-compose.yml | [T1.2.3](subtasks/epic-001/T1.2.3-validate-docker-compose.md) | 1.2.1, 1.2.2 |

### T1.3: Testing Infrastructure & Fixtures

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 1.3.1 | pytest.ini и conftest.py | [T1.3.1](subtasks/epic-001/T1.3.1-pytest-config-conftest.md) | 1.1.1 |
| 1.3.2 | Redis mock fixture | [T1.3.2](subtasks/epic-001/T1.3.2-redis-mock-fixture.md) | 1.3.1 |
| 1.3.3 | Matrix mock fixture | [T1.3.3](subtasks/epic-001/T1.3.3-matrix-mock-fixture.md) | 1.3.1 |
| 1.3.4 | Whisper mock fixture | [T1.3.4](subtasks/epic-001/T1.3.4-whisper-mock-fixture.md) | 1.3.1 |
| 1.3.5 | HTTP mock fixture | [T1.3.5](subtasks/epic-001/T1.3.5-http-mock-fixture.md) | 1.3.1 |

### T1.4: Configuration Management

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 1.4.1 | Базовый модуль конфигурации (Pydantic) | [T1.4.1](subtasks/epic-001/T1.4.1-base-config-module.md) | 1.1.1 |
| 1.4.2 | Загрузка из .env | [T1.4.2](subtasks/epic-001/T1.4.2-env-variable-loading.md) | 1.4.1 |

### T1.5: CI/CD Pipeline

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 1.5.1 | GitHub Actions CI pipeline | [T1.5.1](subtasks/epic-001/T1.5.1-github-actions-ci.md) | 1.3.1, 1.4.1 |
| 1.5.2 | Pre-commit hooks | [T1.5.2](subtasks/epic-001/T1.5.2-pre-commit-hooks.md) | 1.5.1 |

---

## EPIC-002: Bot — Matrix Integration & Audio Ingestion

### T2.1: Matrix Client Wrapper

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 2.1.1 | Базовый класс MatrixClientWrapper | [T2.1.1](subtasks/epic-002/T2.1.1-matrix-client-wrapper-base.md) | 1.4.1 |
| 2.1.2 | Управление комнатами | [T2.1.2](subtasks/epic-002/T2.1.2-matrix-room-management.md) | 2.1.1 |
| 2.1.3 | Обработка входящих сообщений | [T2.1.3](subtasks/epic-002/T2.1.3-matrix-message-handling.md) | 2.1.2 |

### T2.2: Audio Ingestion & Download

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 2.2.1 | Модуль скачивания аудио | [T2.2.1](subtasks/epic-002/T2.2.1-audio-download-module.md) | 2.1.3 |
| 2.2.2 | Валидация форматов аудио | [T2.2.2](subtasks/epic-002/T2.2.2-audio-format-validation.md) | 2.2.1 |

### T2.3: Redis Task Queue Integration

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 2.3.1 | Producer (отправка задач) | [T2.3.1](subtasks/epic-002/T2.3.1-redis-queue-producer.md) | 2.2.2 |
| 2.3.2 | Consumer (потребление задач) | [T2.3.2](subtasks/epic-002/T2.3.2-redis-queue-consumer.md) | 2.3.1 |

### T2.4: Status Notifications

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 2.4.1 | Модуль статусных уведомлений | [T2.4.1](subtasks/epic-002/T2.4.1-status-notification-module.md) | 2.3.1 |

### T2.5: Bot Message Listener & Graceful Shutdown

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 2.5.1 | Основной цикл бота | [T2.5.1](subtasks/epic-002/T2.5.1-bot-main-loop.md) | 2.4.1 |
| 2.5.2 | Graceful shutdown бота | [T2.5.2](subtasks/epic-002/T2.5.2-bot-graceful-shutdown.md) | 2.5.1 |

---

## EPIC-003: Worker — Audio Processing & Transcription

### T3.1: Audio Conversion (ffmpeg)

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 3.1.1 | Модуль конвертации аудио | [T3.1.1](subtasks/epic-003/T3.1.1-audio-conversion-module.md) | 1.4.2 |
| 3.1.2 | Обрезка аудио для Whisper | [T3.1.2](subtasks/epic-003/T3.1.2-audio-trimming.md) | 3.1.1 |

### T3.2: Whisper Transcription Integration

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 3.2.1 | Модуль транскрипции Whisper | [T3.2.1](subtasks/epic-003/T3.2.1-whisper-transcription-module.md) | 3.1.2 |
| 3.2.2 | VAD Detection | [T3.2.2](subtasks/epic-003/T3.2.2-vad-detection.md) | 3.2.1 |

### T3.3: Task Processing Pipeline

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 3.3.1 | Pipeline обработки задач | [T3.3.1](subtasks/epic-003/T3.3.1-task-processing-pipeline.md) | 3.2.1 |
| 3.3.2 | Сохранение результатов | [T3.3.2](subtasks/epic-003/T3.3.2-pipeline-results-storage.md) | 3.3.1 |

### T3.4: Error Handling & Logging

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 3.4.1 | Модуль обработки ошибок | [T3.4.1](subtasks/epic-003/T3.4.1-error-handling-module.md) | 3.3.1 |
| 3.4.2 | Логирование в pipeline | [T3.4.2](subtasks/epic-003/T3.4.2-logging-to-pipeline.md) | 3.4.1 |

---

## EPIC-004: Worker — LLM Summarization & PDF Generation

### T4.1: LLM API Integration

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 4.1.1 | LLM API Client | [T4.1.1](subtasks/epic-004/T4.1.1-llm-api-client.md) | 1.4.2 |
| 4.1.2 | Парсинг ответов LLM | [T4.1.2](subtasks/epic-004/T4.1.2-llm-response-parsing.md) | 4.1.1 |

### T4.2: Markdown Template & Chunking

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 4.2.1 | Markdown Template Engine | [T4.2.1](subtasks/epic-004/T4.2.1-markdown-template-engine.md) | 4.1.2 |
| 4.2.2 | Text Chunking для LLM | [T4.2.2](subtasks/epic-004/T4.2.2-text-chunking.md) | 4.2.1 |

### T4.3: PDF Generation

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 4.3.1 | PDF Generator модуль | [T4.3.1](subtasks/epic-004/T4.3.1-pdf-generator-module.md) | 4.2.1 |
| 4.3.2 | Стилизация PDF | [T4.3.2](subtasks/epic-004/T4.3.2-pdf-styling.md) | 4.3.1 |

### T4.4: End-to-End Summary Pipeline

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 4.4.1 | Summary Pipeline | [T4.4.1](subtasks/epic-004/T4.4.1-summary-pipeline.md) | 4.3.1, 4.1.1 |
| 4.4.2 | LLM Prompt Engineering | [T4.4.2](subtasks/epic-004/T4.4.2-llm-prompt-engineering.md) | 4.4.1 |

---

## EPIC-005: Bot — Result Delivery

### T5.1: Redis Pub/Sub for Results

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 5.1.1 | Result Publisher (worker) | [T5.1.1](subtasks/epic-005/T5.1.1-redis-pubsub-result-publisher.md) | 4.4.1 |
| 5.1.2 | Result Subscriber (bot) | [T5.1.2](subtasks/epic-005/T5.1.2-redis-pubsub-result-subscriber.md) | 5.1.1 |

### T5.2: Bot Result Consumer & Media Upload

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 5.2.1 | Bot Result Consumer | [T5.2.1](subtasks/epic-005/T5.2.1-bot-result-consumer.md) | 5.1.2 |
| 5.2.2 | Media Upload в Matrix | [T5.2.2](subtasks/epic-005/T5.2.2-media-upload-to-bot.md) | 5.2.1 |

### T5.3: Bot Error Handling for Result Delivery

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 5.3.1 | Обработка ошибок доставки | [T5.3.1](subtasks/epic-005/T5.3.1-bot-error-handling-results.md) | 5.2.2 |

### T5.4: Bot Graceful Shutdown for Result Consumer

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 5.4.1 | Graceful shutdown consumer'а | [T5.4.1](subtasks/epic-005/T5.4.1-bot-graceful-shutdown-results.md) | 5.3.1 |

---

## EPIC-006: Reliability & Error Handling

### T6.1: Retry with Exponential Backoff

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 6.1.1 | Retry механизм | [T6.1.1](subtasks/epic-006/T6.1.1-retry-mechanism.md) | 1.4.2 |

### T6.2: Dead Letter Queue

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 6.2.1 | Dead Letter Queue | [T6.2.1](subtasks/epic-006/T6.2.1-dead-letter-queue.md) | 6.1.1 |

### T6.3: Timeout Management

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 6.3.1 | Управление таймаутами | [T6.3](tasks/epic-006/T6.3-timeout-management.md) | 6.1.1 |

### T6.4: Duplicate Task Prevention

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 6.4.1 | Предотвращение дублирования | [T6.4](tasks/epic-006/T6.4-duplicate-task-prevention.md) | 6.1.1 |

---

## EPIC-007: Observability & Configuration

### T7.1: JSON Structured Logging

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 7.1.1 | JSON Logger | [T7.1.1](subtasks/epic-007/T7.1.1-json-logger.md) | 1.4.1 |

### T7.2: Health Checks

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 7.2.1 | Health Check Endpoint | [T7.2.1](subtasks/epic-007/T7.2.1-health-check-endpoint.md) | 7.1.1 |

### T7.3: Metrics Collection

| № | Подзадача | Файл | Зависимости |
|---|-----------|------|-------------|
| 7.3.1 | Metrics Collector | [T7.3.1](subtasks/epic-007/T7.3.1-metrics-collector.md) | 7.2.1 |

---

## Принципы каждой задачи

Каждая задача и подзадача в детальных файлах содержит:

1. **Spec** — чёткий ввод → обработка → вывод (Spec-Driven Development)
2. **TDD** — требование писать тесты до реализации (Red → Green → Refactor)
3. **Критерии приёмки** — проверяемые условия, при которых задача считается выполненной
4. **Граничные случаи** — edge cases, которые тесты должны покрыть
5. **Пошаговый план** — последовательность шагов от создания теста до финальной проверки
6. **Зависимости** — какие подзадачи должны быть завершены перед началом

## Структура файлов

```
docs/
├── epics/                      # 7 epic файлов (описание + критерии приёмки)
│   ├── epic-001-project-foundation.md
│   ├── epic-002-bot-matrix-audio.md
│   ├── epic-003-worker-audio-transcription.md
│   ├── epic-004-worker-llm-pdf.md
│   ├── epic-005-bot-result-delivery.md
│   ├── epic-006-reliability-errors.md
│   └── epic-007-observability-config.md
├── tasks/                      # 29 task файлов (TDD-требования, план, критерии)
│   ├── epic-001/ (5 задач)
│   ├── epic-002/ (5 задач)
│   ├── epic-003/ (4 задачи)
│   ├── epic-004/ (4 задачи)
│   ├── epic-005/ (4 задачи)
│   ├── epic-006/ (4 задачи)
│   └── epic-007/ (3 задачи)
└── subtasks/                   # 54 subtask файлов (пошаговый план)
    ├── epic-001/ (15 подзадач)
    ├── epic-002/ (10 подзадач)
    ├── epic-003/ (8 подзадач)
    ├── epic-004/ (8 подзадач)
    ├── epic-005/ (6 подзадач)
    ├── epic-006/ (4 подзадачи)
    └── epic-007/ (3 подзадачи)
```
