# EPIC-005: Bot — Result Delivery

## Описание

Бот слушает Redis pub/sub канал `task_results`, получает пути к PDF-файлам, загружает их в Matrix и отправляет в исходную комнату.

**Зависимости:** EPIC-002 (Bot — Matrix Integration), EPIC-004 (Worker — LLM + PDF)

**Цель приёмки эпика:**
- Бот подписан на Redis pub/sub канал `task_results`
- При получении результата: парсит `room_id|transcript_pdf|summary_pdf`
- Загружает оба PDF-файла через Matrix Media API
- Отправляет файлы в комнату как `m.file`
- Обработка ошибок: файл не найден, upload failed, room not found

---

## T5.1: Redis pub/sub listener

**Длительность:** ~1.5 часа  
**Зависимости:** T1.3 (Fixtures)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Redis pub/sub канал `task_results` | Слушатель сообщений, парсинг, валидация | Распарсенный результат: room_id, transcript_path, summary_path |

### Критерии приёмки
- [ ] `bot/results.py` — класс `ResultListener` с методом `listen(callback)`
- [ ] Подписка на канал `task_results`
- [ ] Парсинг сообщения: `"room_id|transcript_path|summary_path"`
- [ ] Валидация: 3 поля, непустые
- [ ] Async: работает внутри asyncio loop
- [ ] Обработка ошибок парсинга: log error, continue

### Граничные случаи
- Сообщение не содержит `|` → ValueError, log error, continue
- Сообщение содержит 2 `|` → 2 поля → ValueError
- Сообщение содержит 4 `|` → 4 поля → ValueError
- Пустое сообщение → ValueError
- room_id пустой → ValueError
- Путь к файлу пустой → ValueError

### Пошаговый план
1. Создать `bot/results.py`:
   ```python
   import asyncio
   import logging
   import redis
   
   logger = logging.getLogger(__name__)
   
   RESULT_CHANNEL = "task_results"
   
   class ResultListener:
       def __init__(self, redis_conn: redis.Redis):
           self.redis_conn = redis_conn
           self.pubsub = redis_conn.pubsub()
           self._running = False
       
       async def listen(self, callback):
           """Слушает канал task_results и вызывает callback для каждого результата."""
           self.pubsub.subscribe(RESULT_CHANNEL)
           self._running = True
           
           logger.info("ResultListener subscribed to '%s'", RESULT_CHANNEL)
           
           while self._running:
               try:
                   message = await asyncio.get_event_loop().run_in_executor(
                       None, self._blocking_receive
                   )
                   if message and message.get("type") == "message":
                       data = message["data"].decode()
                       try:
                           await callback(data)
                       except Exception as e:
                           logger.error("Error in result callback: %s", e)
               except Exception as e:
                   logger.error("ResultListener error: %s", e)
                   await asyncio.sleep(1)
       
       def _blocking_receive(self):
           return self.pubsub.get_message(timeout=1.0)
       
       def stop(self):
           self._running = False
           self.pubsub.unsubscribe(RESULT_CHANNEL)
           self.pubsub.close()
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_bot_results.py`:
  - `test_result_listener_subscribes_to_channel()` — проверяет pubsub.subscribe("task_results")
  - `test_result_listener_parses_valid_message()` — "room1|/path/t.pdf|/path/s.pdf" → 3 поля
  - `test_result_listener_invalid_message_few_fields()` — "room1|/path/t.pdf" → ValueError
  - `test_result_listener_invalid_message_empty()` — "" → ValueError
  - `test_result_listener_stops_listening()` — stop() → _running = False
  - `test_result_listener_unsubscribes_on_stop()` — проверяет unsubscribe
  - `test_result_listener_callback_error_does_not_crash()` — callback raises → log error, continue

---

## T5.2: File upload to Matrix

**Длительность:** ~1.5 часа  
**Зависимости:** T5.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| room_id + paths к PDF-файлам | Проверка файлов, upload через Matrix Media API, отправка как m.file | Файлы отправлены в комнату |

### Критерии приёмки
- [ ] `bot/upload.py` — функция `send_results(client, room_id, transcript_path, summary_path)`
- [ ] Проверка что оба PDF-файла существуют и не пусты
- [ ] Upload каждого файла через `await client.upload(file, content_type="application/pdf")`
- [ ] Отправка m.file с content_uri
- [ ] Логирование: upload success, content_uri
- [ ] Обработка ошибок: FileNotFoundError, MatrixError

### Граничные случаи
- PDF-файл не существует → ValueError с путём
- PDF-файл пустой → ValueError
- Upload вернул ошибку → retry (1 раз)
- Room не существует → MatrixError
- Оба файла не существуют → ValueError с обоими путями
- Upload timeout → retry

### Пошаговый план
1. Создать `bot/upload.py`:
   ```python
   import os
   import logging
   from nio import MatrixError
   
   logger = logging.getLogger(__name__)
   
   async def send_results(client, room_id: str, transcript_path: str, summary_path: str):
       # Проверка файлов
       for path, name in [(transcript_path, "transcript"), (summary_path, "summary")]:
           if not os.path.exists(path):
               raise FileNotFoundError(f"{name} PDF not found: {path}")
           if os.path.getsize(path) == 0:
               raise ValueError(f"{name} PDF is empty: {path}")
       
       # Upload и отправка
       for path, name in [(transcript_path, "transcript"), (summary_path, "summary")]:
           try:
               with open(path, "rb") as f:
                   resp, _ = await client.upload(f, content_type="application/pdf")
               
               await client.room_send(room_id, "m.room.message", {
                   "msgtype": "m.file",
                   "body": f"{name}.pdf",
                   "url": resp.content_uri,
                   "info": {"mimetype": "application/pdf"}
               })
               logger.info("Sent %s.pdf to %s: %s", name, room_id, resp.content_uri)
               
           except MatrixError as e:
               logger.error("Failed to send %s.pdf to %s: %s", name, room_id, e)
               raise
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_bot_upload.py`:
  - `test_send_results_checks_file_exists()` — файл не существует → FileNotFoundError
  - `test_send_results_checks_file_not_empty()` — пустой файл → ValueError
  - `test_send_results_calls_upload()` — мокает upload, проверяет что вызван
  - `test_send_results_calls_room_send()` — мокает room_send, проверяет m.file с correct msgtype
  - `test_send_results_sends_both_files()` — оба PDF отправлены
  - `test_send_results_matrix_error_raises()` — MatrixError → raise
  - `test_send_results_logs_success()` — логгер вызван с info

---

## T5.3: Result processing and delivery flow

**Длительность:** ~1.5 часа  
**Зависимости:** T5.1, T5.2

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Redis message `room_id|transcript|summary` | Parse → validate → send_results → notify user | Результаты доставлены |

### Критерии приёмки
- [ ] `bot/delivery.py` — функция `handle_result(message, client, room_id)`
- [ ] Parse message → 3 поля
- [ ] Validate file paths exist
- [ ] Call `send_results()`
- [ ] Notify user: "Результаты готовы!"
- [ ] Обработка ошибок: уведомить пользователя о сбое

### Граничные случаи
- Результат для уже покинутой комнаты → MatrixError → log, продолжить
- Результат дублируется (pub/sub at-least-once) → проверка по room_id + timestamp
- PDF-файл удалён worker'ом до отправки → FileNotFoundError

### Пошаговый план
1. Создать `bot/delivery.py`:
   ```python
   import logging
   from bot.upload import send_results
   
   logger = logging.getLogger(__name__)
   
   async def handle_result(message: str, client, room_id: str):
       parts = message.split("|")
       if len(parts) != 3:
           raise ValueError(f"Invalid result message format: {message!r}")
       
       _, transcript_path, summary_path = parts
       
       try:
           await send_results(client, room_id, transcript_path, summary_path)
           await client.room_send(room_id, "m.room.message", {
               "msgtype": "m.notice",
               "body": "Результаты готовы! Транскрипция и саммари отправлены."
           })
       except Exception as e:
           logger.error("Failed to deliver results to %s: %s", room_id, e)
           try:
               await client.room_send(room_id, "m.room.message", {
                   "msgtype": "m.notice",
                   "body": f"Ошибка при отправке результатов: {e}"
               })
           except Exception:
               logger.error("Could not notify user about delivery failure")
   ```
2. Интегрировать в `bot/main.py` — ResultListener + handle_result
3. Написать тесты

### Тесты (TDD)
- `tests/unit/test_bot_delivery.py`:
  - `test_handle_result_parses_message()` — проверяет парсинг
  - `test_handle_result_calls_send_results()` — send_results вызван
  - `test_handle_result_notifies_user_on_success()` — m.notice "Результаты готовы"
  - `test_handle_result_notifies_user_on_failure()` — send_results raises → error notice
  - `test_handle_result_invalid_message_raises()` — wrong format → ValueError

---

## Интеграционный тест

### `tests/integration/test_bot_result_delivery.py`
- `test_full_result_flow()` — Redis publish → ResultListener → send_results
- `test_delivery_with_real_audio_md()` — использует `tests/fixtures/short.wav` → MD-результат → отправлен в Matrix
- `test_delivery_with_real_audio_pdf()` — использует `tests/fixtures/medium.mp3` → PDF-результат → отправлен в Matrix
- `test_delivery_error_handling()` — Redis unavailable → error notice sent to user
