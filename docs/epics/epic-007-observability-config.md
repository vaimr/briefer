# EPIC-007: Observability & Configuration

## Описание

Структурированное логирование (STDOUT only, JSON format), health-check endpoints, metrics (количество задач, время обработки, ошибки), конфигурация через файл/переменные.

**Зависимости:** EPIC-001 (Foundation)

**Цель приёмки эпика:**
- JSON-формат логирования для bot и worker, вывод ТОЛЬКО в STDOUT (никаких локальных файлов)
- Health-check endpoint: `/health` возвращает status + uptime + component status
- Prometheus metrics endpoint: `/metrics` в формате Prometheus text/plain
- Metrics: количество обработанных задач, время обработки, количество ошибок
- Конфигурация через `.env` с fallback на defaults

---

## T7.1: Structured logging (JSON)

**Длительность:** ~1.5 часа  
**Зависимости:** T1.4 (Config)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Python logger | JSON-форматирование: timestamp, level, component, message, extra fields | Логи в JSON для docker-compose logging |

### Критерии приёмки
- [ ] `bot/logging.py` — функция `setup_logging(component: str, level: str = "INFO") -> None`
- [ ] JSON formatter: `{"timestamp": "...", "level": "...", "component": "...", "message": "...", ...}`
- [ ] Worker: аналогичный `worker/logging.py`
- [ ] Логи выводятся ТОЛЬКО в STDOUT (никаких файловых handlers)
- [ ] Нет файловых логов (ни `/var/log/`, ни `./logs/`, ни `./bot.log`)
- [ ] Optional: структурированные поля для task_id, room_id

### Граничные случаи
- level = "DEBUG" → все логи
- level = "INFO" → info+
- level = "WARNING" → warning+
- level = "ERROR" → error+
- level = "CRITICAL" → critical+
- Non-string message → str(message)

### Пошаговый план
1. Создать `bot/logging.py`:
   ```python
   import logging
   import json
   import sys
   from datetime import datetime, timezone
   
   class JSONFormatter(logging.Formatter):
       def format(self, record):
           log_entry = {
               "timestamp": datetime.now(timezone.utc).isoformat(),
               "level": record.levelname,
               "component": getattr(record, "component", "bot"),
               "message": record.getMessage(),
           }
           if record.exc_info:
               log_entry["exception"] = self.formatException(record.exc_info)
           return json.dumps(log_entry, ensure_ascii=False)
   
   def setup_logging(component: str = "bot", level: str = "INFO"):
       handler = logging.StreamHandler(sys.stdout)
       handler.setFormatter(JSONFormatter())
       
       root = logging.getLogger()
       root.handlers = []
       root.addHandler(handler)
       root.setLevel(getattr(logging, level.upper(), logging.INFO))
       
       # Suppress noisy loggers
       logging.getLogger("urllib3").setLevel(logging.WARNING)
       logging.getLogger("nio").setLevel(logging.WARNING)
   ```
2. Создать `worker/logging.py` аналогично
3. Написать тесты

### Тесты (TDD)
- `tests/unit/test_bot_logging.py`:
  - `test_json_formatter_format()` — проверяет что JSON содержит все поля
  - `test_json_formatter_has_timestamp()` — timestamp в ISO format
  - `test_json_formatter_has_level()` — level = "INFO"
  - `test_json_formatter_has_component()` — component = "bot"
  - `test_json_formatter_has_exception()` — exc_info → exception field
  - `test_setup_logging_sets_handler()` — handler установлен
  - `test_setup_logging_sets_level()` — level = INFO
- `tests/unit/test_worker_logging.py`:
  - Аналогично для worker

---

## T7.2: Health check endpoints

**Длительность:** ~1.5 часа  
**Зависимости:** T7.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| HTTP GET /health | Проверка Redis + component status | JSON: `{"status": "healthy", "uptime": N, "components": {"redis": "ok"}}` |

### Критерии приёмки
- [ ] `bot/health.py` — HTTP endpoint `/health` (через aiohttp или simple HTTP server)
- [ ] `worker/health.py` — аналогичный endpoint
- [ ] Response: `{"status": "healthy"|"degraded"|"unhealthy", "uptime_seconds": N, "components": {...}}`
- [ ] Redis health: ping → pong
- [ ] Uptime: время с момента запуска
- [ ] Port: configurable (default 8081)

### Граничные случаи
- Redis недоступен → status = "degraded", redis = "error"
- Redis полностью недоступен → status = "unhealthy"
- Bot не подключён к Matrix → status = "degraded"
- Uptime = 0 (только что запущен) → OK

### Пошаговый план
1. Добавить `aiohttp>=3.9` в `bot/requirements.txt` и `worker/requirements.txt`
2. Создать `bot/health.py`:
   ```python
   import asyncio
   import time
   import aiohttp
   import logging
   import redis
   
   logger = logging.getLogger(__name__)
   
   _start_time = time.monotonic()
   
   async def get_health(redis_conn: redis.Redis, matrix_client=None) -> dict:
       uptime = time.monotonic() - _start_time
       components = {}
       status = "healthy"
       
       # Redis check
       try:
           result = redis_conn.ping()
           components["redis"] = "ok" if result else "error"
       except Exception as e:
           components["redis"] = f"error: {e}"
           status = "degraded"
       
       # Matrix check (if connected)
       if matrix_client and matrix_client.user_id:
           components["matrix"] = "connected"
       elif matrix_client:
           components["matrix"] = "not_connected"
           status = "degraded"
       
       return {
           "status": status,
           "uptime_seconds": round(uptime, 1),
           "components": components
       }
   
   async def health_handler(request):
       health = await get_health(request.app["redis_conn"], request.app.get("matrix_client"))
       status_code = 200 if health["status"] == "healthy" else 503
       return aiohttp.web.json_response(health, status=status_code)
   
   def register_health_routes(app, redis_conn, matrix_client=None):
       app["redis_conn"] = redis_conn
       app["matrix_client"] = matrix_client
       app.router.add_get("/health", health_handler)
   ```
3. Создать `worker/health.py` аналогично
4. Написать тесты

### Тесты (TDD)
- `tests/unit/test_bot_health.py`:
  - `test_health_healthy_with_redis()` — Redis OK → status = "healthy"
  - `test_health_degraded_no_redis()` — Redis error → status = "degraded"
  - `test_health_has_uptime()` — uptime > 0
  - `test_health_has_components()` — components dict
  - `test_health_handler_returns_200()` — healthy → 200
  - `test_health_handler_returns_503()` — degraded → 503
  - `test_health_matrix_not_connected()` — Matrix не подключён → degraded

---

## T7.3: Metrics collection

**Длительность:** ~1.5 часа  
**Зависимости:** T7.2

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Bot/Worker events | Счётчики и таймеры: задачи принятые/обработанные/ошибки, время обработки | Metrics dict для health + Prometheus-совместимый формат |

### Критерии приёмки
- [ ] `worker/metrics.py` — класс `Metrics` с методами: `task_received()`, `task_completed(duration)`, `task_failed()`, `get_metrics()`
- [ ] Счётчики: tasks_received, tasks_completed, tasks_failed, tasks_dlq
- [ ] Таймеры: task_duration (histogram)
- [ ] `get_metrics()` → dict для health endpoint
- [ ] Optional: `/metrics` endpoint в формате Prometheus

### Граничные случаи
- Метрики обнуляются при рестарте
- Duration = 0 (мгновенная задача) → OK
- Метрики > 1M → Warning
- concurrent tasks → separate counters

### Пошаговый план
1. Создать `worker/metrics.py`:
   ```python
   import time
   import logging
   
   logger = logging.getLogger(__name__)
   
   class Metrics:
       def __init__(self):
           self.tasks_received = 0
           self.tasks_completed = 0
           self.tasks_failed = 0
           self.tasks_dlq = 0
           self.total_duration = 0.0
           self._start_time = time.monotonic()
       
       def task_received(self):
           self.tasks_received += 1
       
       def task_completed(self, duration: float):
           self.tasks_completed += 1
           self.total_duration += duration
       
       def task_failed(self):
           self.tasks_failed += 1
       
       def task_sent_to_dlq(self):
           self.tasks_dlq += 1
       
       def get_metrics(self) -> dict:
           avg_duration = (self.total_duration / self.tasks_completed) if self.tasks_completed > 0 else 0
           return {
               "tasks_received": self.tasks_received,
               "tasks_completed": self.tasks_completed,
               "tasks_failed": self.tasks_failed,
               "tasks_dlq": self.tasks_dlq,
               "avg_duration_seconds": round(avg_duration, 2),
               "uptime_seconds": round(time.monotonic() - self._start_time, 1)
           }
   ```
2. Создать `bot/metrics.py` аналогично (tasks_received, tasks_sent_to_queue)
3. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_metrics.py`:
  - `test_metrics_task_received()` — counter увеличивается
  - `test_metrics_task_completed()` — counter + duration
  - `test_metrics_task_failed()` — counter увеличивается
  - `test_metrics_avg_duration()` — average рассчитан корректно
  - `test_metrics_get_metrics_returns_dict()` — все поля есть

---

## T7.3b: Prometheus metrics endpoint

**Длительность:** ~1.5 часа  
**Зависимости:** T7.3

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| HTTP GET /metrics | Сериализация Metrics в Prometheus text/plain формат | Строка в формате Prometheus: `# HELP tasks_total ...`, `# TYPE tasks_total counter`, `tasks_total{component="worker"} 42` |

### Критерии приёмки
- [ ] `worker/metrics.py` — метод `Metrics.to_prometheus() -> str`
- [ ] Формат: `# HELP <name> <description>\n# TYPE <name> <type>\n<name>{<labels>} <value>\n`
- [ ] Counter: `briefer_tasks_received_total{component="worker"}`, `briefer_tasks_completed_total{component="worker"}`, `briefer_tasks_failed_total{component="worker"}`, `briefer_tasks_dlq_total{component="worker"}`
- [ ] Histogram: `briefer_task_duration_seconds_bucket{component="worker",le="0.1"}`, `le="0.5"`, `le="1.0"`, `le="5.0"`, `le="15.0"`, `le="+Inf"`, `_sum`, `_count`
- [ ] `/metrics` endpoint возвращает `Content-Type: text/plain; version=0.0.4`
- [ ] Bot: аналогичный `/metrics` endpoint (без histogram, только counters)

### Граничные случаи
- Метрики = 0 → всё ещё должны быть в выводе
- concurrent requests к /metrics → safe (read-only)
- Prometheus scrape каждые 15 секунд → не должно блокировать
- Метрики > 10M → Warning

### Пошаговый план
1. Обновить `worker/metrics.py` — добавить `to_prometheus()` метод:
   ```python
   def to_prometheus(self) -> str:
       lines = []
       # Counters
       lines.append(f"# HELP briefer_tasks_received_total Total tasks received by worker")
       lines.append(f"# TYPE briefer_tasks_received_total counter")
       lines.append(f'briefer_tasks_received_total{{component="worker"}} {self.tasks_received}')
       
       lines.append(f"# HELP briefer_tasks_completed_total Total tasks completed by worker")
       lines.append(f"# TYPE briefer_tasks_completed_total counter")
       lines.append(f'briefer_tasks_completed_total{{component="worker"}} {self.tasks_completed}')
       
       lines.append(f"# HELP briefer_tasks_failed_total Total tasks failed by worker")
       lines.append(f"# TYPE briefer_tasks_failed_total counter")
       lines.append(f'briefer_tasks_failed_total{{component="worker"}} {self.tasks_failed}')
       
       lines.append(f"# HELP briefer_tasks_dlq_total Total tasks sent to DLQ")
       lines.append(f"# TYPE briefer_tasks_dlq_total counter")
       lines.append(f'briefer_tasks_dlq_total{{component="worker"}} {self.tasks_dlq}')
       
       # Histogram (simplified)
       lines.append(f"# HELP briefer_task_duration_seconds Task processing duration")
       lines.append(f"# TYPE briefer_task_duration_seconds histogram")
       lines.append(f'briefer_task_duration_seconds_sum{{component="worker"}} {self.total_duration}')
       lines.append(f'briefer_task_duration_seconds_count{{component="worker"}} {self.tasks_completed}')
       
       return "\n".join(lines) + "\n"
   ```
2. Добавить `/metrics` handler в `bot/health.py` и `worker/health.py`
3. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_metrics_prometheus.py`:
  - `test_to_prometheus_has_counters()` — проверяет что все counters присутствуют
  - `test_to_prometheus_has_help_lines()` — каждая метрика имеет # HELP
  - `test_to_prometheus_has_type_lines()` — каждая метрика имеет # TYPE
  - `test_to_prometheus_format_correct()` — формат совпадает с Prometheus spec
  - `test_metrics_handler_returns_text_plain()` — Content-Type = text/plain
  - `test_metrics_handler_returns_200()` — status 200
  - `test_metrics_zero_values_included()` — метрики = 0 → всё ещё в выводе

**Длительность:** ~1 час  
**Зависимости:** T1.4 (Pydantic Config)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| .env + defaults | Валидированная конфигурация с fallback | Config object с типизированными полями |

### Критерии приёмки
- [ ] Конфигурация загружается из `.env` через pydantic-settings
- [ ] Fallback на значения по умолчанию
- [ ] Валидация: обязательные поля, URL format, non-negative integers
- [ ] Документация всех переменных окружения в `.env.example`
- [ ] `docker compose config` — проверка что все переменные подставлены

### Граничные случаи
- .env не существует → fallback на defaults (где возможно)
- .env с пустыми значениями → fallback
- .env с невалидными значениями → ValueError при загрузке
- .env с неизвестными переменными → игнорировать (extra=ignore)

### Пошаговый план
1. Обновить `.env.example` — добавить все переменные:
   ```
   MATRIX_HOMESERVER=https://matrix.example.com
   MATRIX_USER=@transcriber_bot:example.com
   MATRIX_PASSWORD=your_password
   MATRIX_ACCESS_TOKEN=
   REDIS_HOST=redis
   REDIS_PORT=6379
   LLM_API_URL=http://faex:8080/v1
   LLM_MODEL_NAME=qwen3.6-a3b-mtp:35b
   WHISPER_MODEL=large-v3
   DATA_DIR=/data
   TZ=Europe/Moscow
   LOG_LEVEL=INFO
   HEALTH_PORT=8081
   ```
2. Убедиться что BotConfig и WorkerConfig используют pydantic-settings
3. Написать тесты

### Тесты (TDD)
- `tests/unit/test_config.py`:
  - `test_config_loads_from_env()` — переменные → config
  - `test_config_fallback_defaults()` — без переменных → defaults
  - `test_config_missing_required_raises()` — обязательное поле → ValueError
  - `test_config_invalid_url_raises()` — невалидный URL → ValueError
  - `test_config_extra_vars_ignored()` — unknown vars → ignored

---

## Интеграционный тест

### `tests/integration/test_observability.py`
- `test_health_endpoint_healthy()` — Docker compose up → GET /health → 200
- `test_health_endpoint_degraded()` — остановить Redis → GET /health → 503
- `test_json_logging_stdout_only()` — бот запускается → логи в JSON, нет файловых логов
- `test_metrics_available()` — воркер обрабатывает задачу → metrics обновлены
- `test_prometheus_metrics_endpoint()` — GET /metrics → Content-Type=text/plain → содержит counters
- `test_prometheus_metrics_format()` — парсит вывод Prometheus → все метрики present
- `test_no_log_files_created()` — после обработки задачи нет файлов логов на диске
