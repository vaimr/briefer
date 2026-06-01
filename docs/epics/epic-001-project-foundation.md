# EPIC-001: Foundation — Инфраструктура проекта

## Описание

Создание базовой структуры проекта: директории, Docker-образы, конфигурация, тестовый фреймворк, CI-скелет. Без этого фундамента невозможно безопасно разрабатывать ни бота, ни воркера.

**Зависимости:** нет (стартовый эпик)

**Цель приёмки эпика:**
- `docker compose build` проходит без ошибок для сервисов `bot` и `worker` (multi-stage builds)
- `docker compose up redis` запускает Redis с healthcheck
- `pytest` запускается и находит тесты, включая интеграционные с реальными аудио
- Конфигурация загружается из `.env` с валидацией обязательных полей
- `.gitignore` корректно игнорирует sensitive данные
- `tests/fixtures/` содержит минимум 3 валидных аудиофайла (WAV, MP3, FLAC)
- Размер bot-образа < 500MB, worker-образа < 1.5GB

---

## T1.1: Директорная структура и пакетный layout

**Длительность:** ~1 час  
**Зависимости:** нет

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Пустая директория проекта | Создание директорий и файлов-заглушек | Структура: `bot/`, `worker/`, `data/`, `tests/`, `tests/unit/`, `tests/integration/`, `tests/fixtures/` |

### Критерии приёмки
- [ ] Все директории созданы
- [ ] `tests/conftest.py` существует с базовыми fixtures
- [ ] `tests/fixtures/` содержит тестовые аудиофайлы (или заглушки)
- [ ] `data/` существует и добавлен в `.gitignore`

### Граничные случаи
- Пустая директория `data/` не должна попадать в git (git не хранит пустые директории) → нужен `.gitkeep`
- Директория `tests/fixtures/` должна содержать хотя бы один `.gitkeep`

### Пошаговый план
1. Создать директории: `bot/`, `worker/`, `data/`, `tests/`, `tests/unit/`, `tests/integration/`, `tests/fixtures/`
2. Создать `tests/fixtures/.gitkeep`
3. Создать `data/.gitkeep`
4. Проверить `.gitignore` — убедиться, что `data/`, `__pycache__/`, `*.pyc`, `.env` игнорируются
5. Создать `tests/conftest.py` с базовыми fixtures (см. T1.3)

### Тесты (TDD)
- Нет кода для тестирования — проверка через `ls` и `git status`

---

## T1.2: Docker Compose и Dockerfiles

**Длительность:** ~1.5 часа  
**Зависимости:** T1.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Существующие `bot/bot.py`, `worker/worker.py` | Multi-stage Docker-файлы: stage 1 = build (зависимости), stage 2 = runtime (минимальный образ) | `docker compose build` проходит; все 3 сервиса (redis, bot, worker) запускаются; размер образа минимизирован |

### Критерии приёмки
- [ ] `bot/Dockerfile` — multi-stage: `python:3.11-slim` → `COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages`, CMD python bot.py
- [ ] `worker/Dockerfile` — multi-stage: `python:3.11-slim` → `COPY --from=builder`, apt-get в отдельном stage, CMD python worker.py
- [ ] `docker-compose.yml` — 3 сервиса, healthcheck для Redis, depends_on с condition, volumes, environment
- [ ] `docker compose build` завершается без ошибок
- [ ] `docker compose up -d redis && docker compose exec redis redis-cli ping` возвращает `PONG`
- [ ] Размер образа worker < 1.5 GB (multi-stage оптимизация)
- [ ] Размер образа bot < 500 MB (multi-stage оптимизация)

### Граничные случаи
- Multi-stage: builder stage должен иметь все build-зависимости, runtime stage — только runtime
- Модель Whisper должна быть предзагружена в Dockerfile (RUN python -c "...")
- `extra_hosts` для `faex:host-gateway` — проверка что хост доступен
- Шрифты для Cyrillic PDF должны быть в runtime stage (lmodern, texlive-fonts-recommended)

### Пошаговый план
1. Обновить `bot/Dockerfile` в multi-stage формате:
   ```dockerfile
   # Stage 1: Build dependencies
   FROM python:3.11-slim AS builder
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
   
   # Stage 2: Runtime
   FROM python:3.11-slim
   COPY --from=builder /install /usr/local
   WORKDIR /app
   COPY bot/ .
   CMD ["python", "bot.py"]
   ```
2. Обновить `worker/Dockerfile` в multi-stage формате:
   ```dockerfile
   # Stage 1: Build dependencies
   FROM python:3.11-slim AS builder
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
   
   # Stage 2: Runtime
   FROM python:3.11-slim
   # System deps
   RUN apt-get update && apt-get install -y --no-install-recommends \
       ffmpeg \
       pandoc \
       texlive-latex-recommended \
       texlive-latex-extra \
       texlive-fonts-recommended \
       lmodern \
       && rm -rf /var/lib/apt/lists/*
   
   COPY --from=builder /install /usr/local
   WORKDIR /app
   COPY worker/ .
   CMD ["python", "worker.py"]
   ```
3. Проверить `docker-compose.yml` — все переменные, volumes, healthcheck
4. Запустить `docker compose build --no-cache`
5. Запустить `docker compose up -d redis` и проверить healthcheck
6. Проверить размеры образов: `docker images`

### Тесты (TDD)
- `tests/integration/test_docker.py`:
  - `test_redis_healthcheck_passes()` — запускает redis, проверяет `redis-cli ping`
  - `test_bot_image_builds()` — собирает образ bot, проверяет exit code 0
  - `test_worker_image_builds()` — собирает образ worker, проверяет exit code 0
  - `test_worker_has_ffmpeg()` — проверяет что ffmpeg доступен внутри worker-образа
  - `test_worker_has_pandoc()` — проверяет что pandoc доступен внутри worker-образа
  - `test_worker_has_cyrillic_fonts()` — проверяет что lmodern доступен
  - `test_bot_image_size_under_500mb()` — проверяет что размер bot-образа < 500MB
  - `test_worker_image_size_under_1_5gb()` — проверяет что размер worker-образа < 1.5GB

---

## T1.3: Тестовый фреймворк и fixtures

**Длительность:** ~2 часа  
**Зависимости:** T1.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| pytest, pytest-asyncio, pytest-mock | Настройка conftest.py с fixtures для Redis, Matrix, файлов | Тесты могут мокировать Redis, Matrix Client, создавать тестовые аудиофайлы |

### Критерии приёмки
- [ ] `pyproject.toml` или `requirements.txt` содержит: `pytest`, `pytest-asyncio`, `pytest-mock`, `pytest-cov`, `pytest-timeout`
- [ ] `tests/conftest.py` содержит:
  - `redis_client()` — fixture с моком Redis (redis.mock или unittest.mock)
  - `temp_audio_file()` — fixture, создаёт временный WAV-файл для тестов
  - `temp_dir()` — fixture для временных директорий
  - `matrix_client_mock()` — fixture с моком AsyncClient
  - `real_audio_files()` — fixture, возвращает path к тестовым аудиофайлам в `tests/fixtures/`
- [ ] `pytest --collect-only` находит все fixtures
- [ ] Пустой тест проходит (`assert True`)
- [ ] `tests/fixtures/` содержит минимум 3 тестовых аудиофайла:
  - `short.wav` — ~3 секунды, 16kHz mono WAV
  - `medium.mp3` — ~30 секунд, 44.1kHz stereo MP3
  - `long.flac` — ~3 минуты, 16kHz mono FLAC

### Граничные случаи
- `pytest-asyncio` mode = "auto" для async-тестов
- Fixtures должны быть изолированы — каждая тестовая функция получает свежий мокированный Redis
- Файл `temp_audio_file()` должен быть валидным WAV (можно сгенерировать через `scipy.io.wavfile` или `pydub`)
- Реальные аудиофайлы должны быть валидными (проверить через `ffmpeg -i`)
- Файлы должны покрывать разные sample rates и каналы

### Пошаговый план
1. Создать `tests/requirements-dev.txt`:
   ```
   pytest>=8.0
   pytest-asyncio>=0.23
   pytest-mock>=3.14
   pytest-cov>=5.0
   pydub>=0.25
   pytest-timeout>=2.3
   ```
2. Создать `tests/conftest.py`:
   - Импорт fixtures: `pytest_mock`, `tempfile`, `pathlib`
   - `@pytest.fixture def redis_mock()` — создаёт `MockRedis` с методами `rpush`, `blpop`, `publish`, `pubsub`
   - `@pytest.fixture def temp_audio_wav(tmp_path)` — генерирует 1-секундный WAV-файл
   - `@pytest.fixture def temp_dir(tmp_path)` — возвращает `tmp_path`
   - `@pytest.fixture def matrix_client_mock(mocker)` — мокает `AsyncClient`
3. Создать `tests/unit/__init__.py` и `tests/integration/__init__.py`
4. Создать `tests/fixtures/.gitkeep`
5. Создать `tests/test_placeholder.py` с `assert True`
6. Запустить `pytest --collect-only` и убедиться что fixtures видны

### Тесты (TDD)
- `tests/test_conftest.py`:
  - `test_redis_mock_rpush()` — вызывает `rpush` на моке, проверяет что вызван
  - `test_redis_mock_blpop_returns_none_timeout()` — проверяет поведение timeout
  - `test_temp_audio_wav_is_valid()` — проверяет что файл существует и имеет расширение .wav
  - `test_temp_dir_is_clean()` — проверяет что tmp_path пуст на входе
  - `test_matrix_client_mock_has_login()` — проверяет что mock имеет метод login
  - `test_real_audio_files_exist()` — проверяет что short.wav, medium.mp3, long.flac существуют
  - `test_real_audio_files_are_valid()` — проверяет что файлы валидны через `subprocess.run(['ffprobe', ...])`
  - `test_real_audio_files_have_correct_sample_rates()` — short.wav = 16kHz, medium.mp3 = 44.1kHz

---

## T1.4: Конфигурация на Pydantic Settings

**Длительность:** ~1.5 часа  
**Зависимости:** T1.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Переменные окружения (.env) | Pydantic BaseSettings с валидацией обязательных полей | `BotConfig` и `WorkerConfig` — типизированные, самодокументируемые конфиги |

### Критерии приёмки
- [ ] `bot/config.py` — класс `BotConfig(BaseSettings)` с полями: `matrix_homeserver`, `matrix_user`, `matrix_password` (optional), `matrix_access_token` (optional), `redis_host`, `redis_port`
- [ ] `worker/config.py` — класс `WorkerConfig(BaseSettings)` с полями: `redis_host`, `redis_port`, `llm_api_url`, `llm_model_name`, `whisper_model`, `data_dir`, `tz`
- [ ] Обязательные поля (homeserver, user, redis_host) — ValueError при отсутствии
- [ ] `matrix_password` и `matrix_access_token` — хотя бы один должен быть указан (кастомный валидатор)
- [ ] Типы: `redis_port: int = 6379`, `whisper_model: str = "large-v3"`, `data_dir: str = "/data"`

### Граничные случаи
- `matrix_password` и `matrix_access_token` — валидатор: если оба None → ValueError
- `matrix_homeserver` — валидация URL (должен начинаться с https://)
- `llm_api_url` — валидация URL
- Значения по умолчанию для необязательных полей

### Пошаговый план
1. Добавить `pydantic-settings>=2.0` в `bot/requirements.txt` и `worker/requirements.txt`
2. Создать `bot/config.py`:
   ```python
   from pydantic_settings import BaseSettings
   from pydantic import field_validator
   
   class BotConfig(BaseSettings):
       matrix_homeserver: str
       matrix_user: str
       matrix_password: str | None = None
       matrix_access_token: str | None = None
       redis_host: str = "redis"
       redis_port: int = 6379
   
       @field_validator("matrix_homeserver")
       @classmethod
       def validate_homeserver(cls, v: str) -> str:
           if not v.startswith(("http://", "https://")):
               raise ValueError("matrix_homeserver must be a valid URL")
           return v
   
       @field_validator("matrix_password", "matrix_access_token")
       @classmethod
       def validate_at_least_one_auth(cls, v, info) -> str:
           # Проверяем что хотя бы один из password/token указан
           ...
   ```
3. Создать `worker/config.py` аналогично
4. Написать тесты

### Тесты (TDD)
- `tests/unit/test_bot_config.py`:
  - `test_config_loads_from_env()` — устанавливает переменные окружения, создаёт BotConfig, проверяет поля
  - `test_config_missing_homeserver_raises()` — без MATRIX_HOMESERVER → ValueError
  - `test_config_missing_user_raises()` — без MATRIX_USER → ValueError
  - `test_config_missing_both_auth_raises()` — без password и token → ValueError
  - `test_config_with_token_succeeds()` — только token, без password → OK
  - `test_config_with_password_succeeds()` — только password, без token → OK
  - `test_config_invalid_homeserver_url_raises()` — "not-a-url" → ValueError
  - `test_config_defaults()` — без redis_host/port → значения по умолчанию
- `tests/unit/test_worker_config.py`:
  - Аналогичные тесты для WorkerConfig
  - `test_config_default_whisper_model()` — whisper_model = "large-v3" по умолчанию
  - `test_config_default_data_dir()` — data_dir = "/data" по умолчанию

---

## T1.5: CI-скелет и pre-commit

**Длительность:** ~1 час  
**Зависимости:** T1.3, T1.4

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Python-проект | `.github/workflows/ci.yml` + pre-commit config | PR-пайплайн: lint → test → coverage threshold |

### Критерии приёмки
- [ ] `.github/workflows/ci.yml` — workflow на push/PR: устанавливает Python 3.11, pip install, pytest
- [ ] `.pre-commit-config.yaml` — black, isort, flake8 (или ruff)
- [ ] `tox.ini` или `Makefile` с целями: `make test`, `make lint`, `make docker-build`

### Граничные случаи
- CI должен работать без доступа к Docker (тесты юнитов) и с Docker (интеграционные)
- Coverage threshold: минимум 60% для MVP

### Пошаговый план
1. Создать `.pre-commit-config.yaml` с hooks: black (88), isort, flake8
2. Создать `.github/workflows/ci.yml`:
   - Trigger: push, pull_request
   - Jobs: lint (black --check, flake8), test (pytest --cov)
3. Создать `Makefile`:
   ```makefile
   test: pytest tests/
   lint: black --check . isort --check . flake8 .
   docker-build: docker compose build
   ```
4. Запустить `make test` локально и убедиться что проходит

### Тесты (TDD)
- Нет кода для тестирования — проверка через запуск CI-локально

---

## Тесты эпика (интеграция)

### `tests/integration/test_docker_compose.py`
- `test_redis_starts_and_healthy()` — `docker compose up redis`, healthcheck проходит
- `test_bot_starts_with_env()` — `docker compose up bot`, бот подключается к Redis
- `test_worker_starts_with_env()` — `docker compose up worker`, воркер подключается к Redis
