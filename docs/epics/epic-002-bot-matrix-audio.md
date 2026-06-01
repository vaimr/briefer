# EPIC-002: Bot — Matrix Integration & Audio Ingestion

## Описание

Реализация бота, который слушает Matrix-комнаты, скачивает аудио из сообщений, валидирует форматы и отправляет задачи в Redis-очередь для воркера. Бот также отправляет статусные уведомления (processing, done, error).

**Зависимости:** EPIC-001 (Foundation)
**Целевой сервис:** `bot`

**Цель приёмки эпика:**
- Бот подключается к Matrix, входит в комнаты из конфига
- Бот распознаёт сообщения с аудио-вложениями и игнорирует текстовые/другие типы
- Скачанные аудиофайлы валидируются (формат, размер, длительность)
- Задачи корректно помещаются в Redis-очередь (`transcription_queue`)
- Бот отправляет статусные уведомления в комнату
- Бот корректно завершает работу по SIGTERM (graceful shutdown)

---

## T2.1: Matrix Client Wrapper

**Длительность:** ~2 часа  
**Зависимости:** T1.4.1 (BotConfig)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| `BotConfig` с Matrix-параметрами | `nio.AsyncClient` — login, sync loop, event callbacks | Клиент подключён к Matrix, готов принимать события |

### Критерии приёмки
- [ ] `bot/matrix_client.py` — класс `MatrixClientWrapper` с методами:
  - `connect()` → login с password или token
  - `join_rooms(room_ids: list[str])` → join в указанные комнаты
  - `add_event_callback(callback, event_types)` → регистрация колбэка
  - `room_send(room_id, msgtype, content)` → отправка сообщения
  - `start()` → запуск sync loop (asyncio.Task)
  - `stop()` → остановка sync loop
- [ ] `connect()` использует `BotConfig.matrix_access_token` если указан, иначе `matrix_password`
- [ ] `join_rooms()` — для каждой комнаты: `client.join(room_id)`, логирование успеха/ошибки
- [ ] `start()` запускает `sync_forever` в отдельном `asyncio.Task`
- [ ] `stop()` устанавливает флаг остановки и ждёт завершения task

### Граничные случаи
- `matrix_access_token` и `matrix_password` оба None → ValueError при `connect()`
- `matrix_homeserver` не начинается с `http://` или `https://` → ValueError
- Комната с ID, который не начинается с `!` → лог warn, пропуск
- Ошибка login (неверные credentials) → ValueError с понятным сообщением
- `sync_forever` падает с сетевой ошибкой → retry с backoff (1s, 2s, 4s, ...)

### Пошаговый план
1. Создать `bot/matrix_client.py` с классом `MatrixClientWrapper`
2. Реализовать `__init__` с `BotConfig`
3. Реализовать `connect()` — login через token или password
4. Реализовать `join_rooms()` — join в комнаты из конфига
5. Реализовать `add_event_callback()` — регистрация callback
6. Реализовать `start()` / `stop()` — управление sync loop
7. Реализовать `room_send()` — отправка сообщений
8. Написать тесты

### Тесты (TDD)
- `tests/unit/test_matrix_client.py`:
  - `test_connect_with_token()` — login с access_token
  - `test_connect_with_password()` — login с password (fallback)
  - `test_connect_neither_auth_raises()` — без auth → ValueError
  - `test_join_rooms_joins_each()` — проверяет что вызван join для каждой комнаты
  - `test_join_rooms_skips_invalid_room_id()` — комната без `!` → warn, пропуск
  - `test_start_starts_sync_task()` — проверяет что asyncio.Task создан
  - `test_stop_stops_sync_task()` — проверяет что task остановлен
  - `test_room_sends_message()` — room_send отправляет сообщение, проверяется `_sent_messages`
  - `test_add_event_callback_registers_callback()` — callback добавлен в `_callbacks`

---

## T2.2: Audio Ingestion & Download

**Длительность:** ~1.5 часа  
**Зависимости:** T2.1.1, T2.1.3

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Matrix событие с audio-вложением | Скачивание файла → валидация формата/размера/длительности → сохранение в temp dir | Путь к валидному аудиофайлу или raise на невалидном |

### Критерии приёмки
- [ ] `bot/client.py` — функция `download_audio(event, client, temp_dir)` → `Path`
- [ ] Поддерживаемые форматы: WAV, MP3, FLAC, M4A, OGG, WEBM
- [ ] Максимальный размер: 100 MB (конфигурируемо)
- [ ] Минимальная длительность: 0.5 секунды
- [ ] Максимальная длительность: 4 часа (14400 секунд)
- [ ] Валидация через `ffmpeg.probe` или `mutagen`
- [ ] Файл сохраняется в `temp_dir` с уникальным именем

### Граничные случаи
- Сообщение без вложений → raise `ValueError("No media attachment")`
- Вложение не аудио-типа (изображение, документ) → raise `ValueError`
- Файл > 100 MB → raise `ValueError`
- Файл < 0.5 сек → raise `ValueError`
- Файл > 4 часов → raise `ValueError`
- Невалидный аудиофайл (коррупция) → raise `ValueError`
- Ошибка скачивания (network error) → raise `requests.RequestException`

### Пошаговый план
1. Создать `bot/client.py` с функцией `download_audio()`
2. Реализовать проверку типа вложения (audio/*)
3. Реализовать скачивание через `client.download()`
4. Реализовать валидацию формата через `ffmpeg.probe`
5. Реализовать валидацию размера и длительности
6. Реализовать сохранение в temp dir
7. Написать тесты

### Тесты (TDD)
- `tests/unit/test_client.py`:
  - `test_download_audio_wav()` — WAV файл скачивается и валидируется
  - `test_download_audio_mp3()` — MP3 файл скачивается и валидируется
  - `test_download_audio_flac()` — FLAC файл скачивается и валидируется
  - `test_download_audio_m4a()` — M4A файл скачивается и валидируется
  - `test_download_audio_ogg()` — OGG файл скачивается и валидируется
  - `test_download_audio_webm()` — WEBM файл скачивается и валидируется
  - `test_download_audio_invalid_format_raises()` — PDF/изображение → ValueError
  - `test_download_audio_no_attachment_raises()` — сообщение без вложений → ValueError
  - `test_download_audio_too_large_raises()` — файл > 100MB → ValueError
  - `test_download_audio_too_short_raises()` — файл < 0.5 сек → ValueError
  - `test_download_audio_too_long_raises()` — файл > 4 часов → ValueError
  - `test_download_audio_corrupted_raises()` — невалидный файл → ValueError
  - `test_download_audio_saved_to_temp_dir()` — файл сохраняется в temp dir

---

## T2.3: Redis Task Queue Integration

**Длительность:** ~1.5 часа  
**Зависимости:** T2.2.2

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Валидный аудиофайл + room_id | Формирование задачи → `rpush` в `transcription_queue` | Задача помещена в очередь, номер задачи возвращён |

### Критерии приёмки
- [ ] `bot/config.py` — поле `redis_host: str = "redis"`, `redis_port: int = 6379`
- [ ] `bot/client.py` — функция `enqueue_task(room_id, audio_path)` → `int` (task_id)
- [ ] Формат задачи: `f"{room_id}|{audio_path}"`
- [ ] Очередь: `transcription_queue`
- [ ] `enqueue_task()` использует `rpush`
- [ ] Возвращает количество элементов в очереди после push

### Граничные случаи
- `room_id` пустой → raise `ValueError`
- `audio_path` не существует → raise `FileNotFoundError`
- Redis недоступен → raise `ConnectionError` с retry 3 раза
- Очередь переполнена (теоретически невозможно для Redis, но проверить)

### Пошаговый план
1. Убедиться что `BotConfig` имеет `redis_host` и `redis_port`
2. Создать функцию `enqueue_task()` в `bot/client.py`
3. Реализовать формат задачи: `f"{room_id}|{audio_path}"`
4. Реализовать `rpush` в `transcription_queue`
5. Реализовать retry логику при ошибке подключения
6. Написать тесты

### Тесты (TDD)
- `tests/unit/test_client.py` (продолжение):
  - `test_enqueue_task_formats_correctly()` — формат `room_id|audio_path`
  - `test_enqueue_task_pushes_to_queue()` — проверяет `rpush` вызван с правильной очередью
  - `test_enqueue_task_returns_count()` — возвращает количество элементов
  - `test_enqueue_task_empty_room_id_raises()` — пустой room_id → ValueError
  - `test_enqueue_task_nonexistent_file_raises()` — файл не существует → FileNotFoundError
  - `test_enqueue_task_redis_unavailable_raises()` — Redis недоступен → ConnectionError

---

## T2.4: Status Notifications

**Длительность:** ~1 час  
**Зависимости:** T2.3.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| room_id, status (processing/done/error), message | Формирование статусного сообщения → `room_send` | Статус отправлен в комнату |

### Критерии приёмки
- [ ] `bot/matrix_client.py` — метод `send_status(room_id, status, message)` → None
- [ ] Статусы: `processing`, `done`, `error`
- [ ] Формат сообщения: `[STATUS] message` (Markdown)
- [ ] `processing`: `[⏳ Processing] message`
- [ ] `done`: `[✅ Done] message`
- [ ] `error`: `[❌ Error] message`
- [ ] При ошибке — message содержит описание ошибки

### Граничные случаи
- Статус не из списка → raise `ValueError`
- `room_id` пустой → raise `ValueError`
- `message` пустой или слишком длинный (> 4000 символов) → truncate или raise

### Пошаговый план
1. Создать метод `send_status()` в `MatrixClientWrapper`
2. Реализовать маппинг статусов на эмодзи
3. Реализовать валидацию параметров
4. Реализовать truncate длинных сообщений
5. Написать тесты

### Тесты (TDD)
- `tests/unit/test_matrix_client.py` (продолжение):
  - `test_send_status_processing()` — статус processing → `[⏳ Processing] msg`
  - `test_send_status_done()` — статус done → `[✅ Done] msg`
  - `test_send_status_error()` — статус error → `[❌ Error] msg`
  - `test_send_status_invalid_status_raises()` — неизвестный статус → ValueError
  - `test_send_status_empty_room_raises()` — пустой room_id → ValueError
  - `test_send_status_truncates_long_message()` — сообщение > 4000 символов → truncated

---

## T2.5: Bot Message Listener & Graceful Shutdown

**Длительность:** ~1.5 часа  
**Зависимости:** T2.4.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Matrix-событие (message) | Тип → audio вложение → download → validate → enqueue → status update | Задача обработана, результат в Redis-очереди |

### Критерии приёмки
- [ ] `bot/__main__.py` — основной цикл обработки событий
- [ ] Обработка `m.room.message` с `m.audio`, `m.file`, `m.video` вложениями
- [ ] Игнорирование текстовых сообщений (с помощью `--help` показывается подсказка)
- [ ] Обработка `SIGTERM` → graceful shutdown (статус "stopping", завершение sync loop)
- [ ] Обработка `SIGINT` → то же поведение
- [ ] Логирование каждой стадии: received → downloading → processing → enqueued → status_sent

### Граничные случаи
- Сообщение без вложений → игнорировать (или показать help)
- Вложение не аудио → отправить ошибку в комнату
- Ошибка enqueue → статус "error" в комнату
- SIGTERM во время скачивания → завершить скачивание, затем shutdown
- SIGTERM во время enqueue → завершить enqueue, затем shutdown

### Пошаговый план
1. Обновить `bot/__main__.py`:
   - Загрузка конфига из env
   - Инициализация MatrixClientWrapper
   - Регистрация event callback для `m.room.message`
   - Функция callback: обработка audio → download → enqueue → status
   - Обработка SIGTERM/SIGINT
   - `--help` флаг для показа подсказки по командам
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_bot_main.py`:
  - `test_handle_audio_message_downloads_and_enqueues()` — полный пайплайн
  - `test_handle_non_audio_message_shows_help()` — текстовое сообщение → help_text
  - `test_handle_invalid_audio_sends_error()` — невалидное аудио → статус error
  - `test_handle_enqueue_error_sends_error()` — ошибка enqueue → статус error
  - `test_graceful_shutdown_on_sigterm()` — SIGTERM → shutdown
  - `test_graceful_shutdown_on_sigint()` — SIGINT → shutdown
  - `test_help_flag_shows_usage()` — `--help` → usage info

---

## Тесты эпика (интеграция)

### `tests/integration/test_bot_full_flow.py`
- `test_bot_receives_audio_and_enqueues()` — полный пайплайн: Matrix-событие → download → validate → enqueue
- `test_bot_receives_non_audio_and_ignores()` — текстовое сообщение → игнор
- `test_bot_sends_status_updates()` — статусы processing/done/error отправляются
- `test_bot_graceful_shutdown_stops_sync()` — SIGTERM → sync loop останавливается
