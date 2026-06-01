# EPIC-006: Reliability & Error Handling

## Описание

Добавление надёжности: retry-механизм с exponential backoff, dead letter queue, таймауты задач, дедупликация, graceful shutdown.

**Зависимости:** EPIC-002 (Bot), EPIC-003 (Worker)

**Цель приёмки эпика:**
- Failed задачи retry-ятся до 3 раз с exponential backoff
- После 3 failed → dead letter queue в Redis
- Задачи с таймаутом > 15 минут → abort
- Дубликаты задач (одинаковый audio_path) → игнорируются
- Graceful shutdown для бота и воркера

---

## T6.1: Retry mechanism with exponential backoff

**Длительность:** ~1.5 часа  
**Зависимости:** T1.4 (Config)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Функция + max_retries | Обёртка retry с exponential backoff | Успешное выполнение или raise после max_retries |

### Критерии приёмки
- [ ] `worker/retry.py` — декоратор/функция `retry(func, max_retries=3, base_delay=1.0)`
- [ ] Exponential backoff: delay = base_delay * 2^attempt
- [ ] Retry на: ConnectionError, TimeoutError, HTTP 5xx
- [ ] НЕ retry на: ValueError, 4xx (кроме 429)
- [ ] Логирование каждой попытки
- [ ] Возврат результата последней попытки

### Граничные случаи
- max_retries = 0 → без retry
- max_retries = 1 → одна попытка + один retry
- Функция падает с ValueError → raise без retry
- Функция падает с ConnectionError → retry 3 раза
- Функция падает с HTTP 400 → raise без retry
- Функция падает с HTTP 429 → retry с увеличенным backoff
- Функция падает с HTTP 500 → retry

### Пошаговый план
1. Создать `worker/retry.py`:
   ```python
   import asyncio
   import logging
   import functools
   import time
   
   logger = logging.getLogger(__name__)
   
   RETRYABLE_EXCEPTIONS = (
       ConnectionError,
       TimeoutError,
       RuntimeError,
   )
   
   def retry(func=None, max_retries: int = 3, base_delay: float = 1.0):
       """Декоратор retry с exponential backoff."""
       def decorator(fn):
           @functools.wraps(fn)
           async def wrapper(*args, **kwargs):
               last_error = None
               for attempt in range(max_retries + 1):
                   try:
                       if asyncio.iscoroutinefunction(fn):
                           return await fn(*args, **kwargs)
                       else:
                           return fn(*args, **kwargs)
                   except Exception as e:
                       last_error = e
                       if attempt < max_retries and _is_retryable(e):
                           delay = base_delay * (2 ** attempt)
                           logger.warning(
                               "Retryable error in %s: %s. Attempt %d/%d, retrying in %.1fs",
                               fn.__name__, e, attempt + 1, max_retries, delay
                           )
                           await asyncio.sleep(delay)
                       else:
                           break
               logger.error("All %d retries exhausted for %s: %s", max_retries, fn.__name__, last_error)
               raise last_error
           return wrapper
       return decorator if func is None else decorator(func)
   
   def _is_retryable(exception: Exception) -> bool:
       """Определяет, можно ли retry-нуть ошибку."""
       if isinstance(exception, RETRYABLE_EXCEPTIONS):
           return True
       # HTTP 5xx
       if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
           return exception.response.status_code >= 500
       return False
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_retry.py`:
  - `test_retry_succeeds_on_first_try()` — функция не падает → без retry
  - `test_retry_succeeds_after_failures()` — падает 2 раза, 3-й раз OK → возвращает результат
  - `test_retry_exhausted_raises()` — падает всегда → raise после max_retries
  - `test_retry_not_retryable_exception()` — ValueError → raise без retry
  - `test_retry_with_zero_max_retries()` — max_retries=0 → без retry
  - `test_retry_logs_each_attempt()` — логгер вызван с warning
  - `test_retry_exponential_backoff_timing()` — замеры времени между попытками

---

## T6.2: Dead letter queue

**Длительность:** ~1 час  
**Зависимости:** T6.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Failed задача после max_retries | Push в Redis DLQ `transcription_dlq` с metadata | Задача в DLQ, логирование |

### Критерии приёмки
- [ ] `worker/dlq.py` — функция `send_to_dlq(redis_conn, task_str: str, error: str, max_retries: int) -> None`
- [ ] Формат DLQ-записи: JSON с полями `task`, `error`, `max_retries`, `failed_at`, `room_id`
- [ ] Использует Redis list `transcription_dlq`
- [ ] Логирование: task, error, timestamp
- [ ] Функция `get_dlq_tasks(redis_conn) -> list[dict]` — чтение DLQ

### Граничные случаи
- DLQ > 100 задач → Warning
- JSON serialize error → log, продолжить
- Redis DLQ недоступен → log error, не crash

### Пошаговый план
1. Создать `worker/dlq.py`:
   ```python
   import json
   import logging
   from datetime import datetime, timezone
   import redis
   
   logger = logging.getLogger(__name__)
   
   DLQ_KEY = "transcription_dlq"
   MAX_DLQ_SIZE = 100
   
   def send_to_dlq(redis_conn: redis.Redis, task_str: str, error: str, max_retries: int):
       room_id = task_str.split("|", 1)[0] if "|" in task_str else "unknown"
       
       dlq_entry = {
           "task": task_str,
           "room_id": room_id,
           "error": error,
           "max_retries": max_retries,
           "failed_at": datetime.now(timezone.utc).isoformat()
       }
       
       task_json = json.dumps(dlq_entry, ensure_ascii=False)
       task_id = redis_conn.rpush(DLQ_KEY, task_json)
       
       if task_id > MAX_DLQ_SIZE:
           logger.warning("DLQ size exceeded %d: %d", MAX_DLQ_SIZE, task_id)
       
       logger.error("Task sent to DLQ: room=%s, error=%s", room_id, error)
   
   def get_dlq_tasks(redis_conn: redis.Redis) -> list[dict]:
       tasks = redis_conn.lrange(DLQ_KEY, 0, -1)
       return [json.loads(t) for t in tasks]
   
   def clear_dlq(redis_conn: redis.Redis) -> int:
       return redis_conn.delete(DLQ_KEY)
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_dlq.py`:
  - `test_send_to_dlq_pushes_json()` — проверяет что JSON записан в DLQ
  - `test_dlq_entry_has_all_fields()` — task, room_id, error, max_retries, failed_at
  - `test_get_dlq_tasks_returns_list()` — возвращает list[dict]
  - `test_clear_dlq_removes_all()` — возвращает count
  - `test_send_to_dlq_large_dlq_warns()` — > 100 → warning

---

## T6.3: Task timeout and deduplication

**Длительность:** ~1.5 часа  
**Зависимости:** нет

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Task + timeout + dedup set | Проверка дубликатов, таймаут обработки | Задача обработана или abort по таймауту |

### Критерии приёмки
- [ ] `worker/monitor.py` — функция `process_with_timeout(coro, timeout: int = 900)` — 15 минут
- [ ] `worker/monitor.py` — функция `is_duplicate(redis_conn, audio_path: str) -> bool` — проверка по audio_path
- [ ] Дедупликация: если audio_path уже в обработке → skip
- [ ] Таймаут: asyncio.wait_for с timeout
- [ ] Timeout → send_to_dlq

### Граничные случаи
- Timeout = 0 → без таймаута
- Дубликат → log, skip
- Timeout + DLQ → задача в DLQ
- Дубликат + timeout → дубликат имеет приоритет

### Пошаговый план
1. Создать `worker/monitor.py`:
   ```python
   import asyncio
   import logging
   import redis
   
   logger = logging.getLogger(__name__)
   
   TASK_TIMEOUT = 900  # 15 минут
   DEDUP_TTL = 3600    # 1 час
   
   async def process_with_timeout(coro, timeout: int = TASK_TIMEOUT):
       """Выполняет coroutine с таймаутом."""
       try:
           return await asyncio.wait_for(coro, timeout=timeout)
       except asyncio.TimeoutError:
           raise asyncio.TimeoutError(f"Task timed out after {timeout}s")
   
   def is_duplicate(redis_conn: redis.Redis, audio_path: str) -> bool:
       """Проверяет, обрабатывается ли уже файл."""
       key = f"processing:{audio_path}"
       return bool(redis_conn.get(key))
   
   def mark_processing(redis_conn: redis.Redis, audio_path: str):
       """Мечает файл как обрабатываемый."""
       key = f"processing:{audio_path}"
       redis_conn.set(key, "1", ex=DEDUP_TTL)
   
   def clear_processing(redis_conn: redis.Redis, audio_path: str):
       """Снимает метку обработки."""
       key = f"processing:{audio_path}"
       redis_conn.delete(key)
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_monitor.py`:
  - `test_process_with_timeout_succeeds()` — coroutine завершается → возвращает результат
  - `test_process_with_timeout_exceeded()` — coroutine > timeout → TimeoutError
  - `test_is_duplicate_false()` — ключ не существует → False
  - `test_is_duplicate_true()` — ключ существует → True
  - `test_mark_processing_sets_key()` — set с TTL
  - `test_clear_processing_deletes_key()` — delete ключ
  - `test_mark_and_clear()` — mark → is_duplicate=True, clear → is_duplicate=False

---

## T6.4: Graceful shutdown (both bot and worker)

**Длительность:** ~1 час  
**Зависимости:** T2.5 (Bot shutdown), T3.4 (Worker shutdown)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| SIGTERM/SIGINT | Остановка всех async-операций, закрытие соединений, очистка | Корректный exit code 0 |

### Критерии приёмки
- [ ] Bot: SIGTERM → stop sync_forever → close Redis → exit 0
- [ ] Worker: SIGTERM → stop blpop loop → close Redis → exit 0
- [ ] Логирование: "Shutting down...", "Stopped"
- [ ] Exit code 0 при graceful shutdown
- [ ] Exit code 1 при crash (unhandled exception)

### Пошаговый план
1. Проверить что T2.5 и T3.4 уже реализуют graceful shutdown
2. Добавить integration-тест:
   - Запустить бота → отправить SIGTERM → проверить exit code 0
   - Запустить воркера → отправить SIGTERM → проверить exit code 0
3. Написать тесты

### Тесты (TDD)
- `tests/integration/test_graceful_shutdown.py`:
  - `test_bot_shutdown_on_sigterm()` — SIGTERM → exit 0
  - `test_worker_shutdown_on_sigterm()` — SIGTERM → exit 0
  - `test_bot_shutdown_closes_redis()` — Redis-соединение закрыто
  - `test_worker_shutdown_closes_redis()` — Redis-соединение закрыто

---

## Интеграционный тест

### `tests/integration/test_reliability.py`
- `test_retry_mechanism()` — ConnectionError → retry → success
- `test_dlq_after_max_retries()` — 3 failure → DLQ
- `test_deduplication()` — дубликат задачи → skip
- `test_task_timeout()` — timeout → DLQ
- `test_reliability_with_real_audio()` — использует `tests/fixtures/short.wav` → full flow → DLQ on failure
- `test_reliability_with_long_audio()` — использует `tests/fixtures/long.flac` → timeout → DLQ
