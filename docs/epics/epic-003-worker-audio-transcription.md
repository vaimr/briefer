# EPIC-003: Worker — Audio Processing & Transcription

## Описание

Воркер извлекает задачи из Redis-очереди, конвертирует аудио в WAV (16kHz mono) через ffmpeg, транскрибирует через faster-whisper (large-v3), возвращает текст и длительность.

**Зависимости:** EPIC-001 (Foundation)

**Цель приёмки эпика:**
- Воркер извлекает задачи из Redis `transcription_queue` через `blpop`
- Конвертирует любой формат аудио (mp3, m4a, ogg, webm, wav, flac) в WAV 16kHz mono
- Транскрибирует через Whisper large-v3 с vad_filter и beam_size=5
- Возвращает полный текст транскрипции и длительность аудио
- Обрабатывает ошибки ffmpeg и Whisper

---

## T3.1: Audio conversion (ffmpeg)

**Длительность:** ~1.5 часа  
**Зависимости:** T1.2 (Docker)

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Путь к аудиофайлу любого формата | ffmpeg → WAV 16kHz mono, проверка результатов | Путь к WAV-файлу, длительность аудио |

### Критерии приёмки
- [ ] `worker/audio.py` — функция `convert_to_wav(audio_path: str, output_dir: str) -> tuple[str, float]`
- [ ] Вызывает `ffmpeg -i {audio_path} -ar 16000 -ac 1 -y {wav_path}`
- [ ] Проверяет что ffmpeg завершился с exit code 0
- [ ] Проверяет что WAV-файл создан и не пустой
- [ ] Возвращает `(wav_path, duration_seconds)`
- [ ] Извлекает длительность из stderr ffmpeg или через `pydub`

### Граничные случаи
- Файл не существует → FileNotFoundError
- Файл повреждён → subprocess.CalledProcessError с выводом stderr
- Пустой файл → subprocess.CalledProcessError или duration = 0
- Файл > 1GB → warning в логе, но продолжать
- Формат unsupported → ffmpeg вернёт ошибку
- WAV-файл не создан → FileNotFoundError

### Пошаговый план
1. Создать `worker/audio.py`:
   ```python
   import os
   import subprocess
   import logging
   from pathlib import Path
   
   logger = logging.getLogger(__name__)
   
   def convert_to_wav(audio_path: str, output_dir: str) -> tuple[str, float]:
       if not os.path.exists(audio_path):
           raise FileNotFoundError(f"Audio file not found: {audio_path}")
       
       output_dir = Path(output_dir)
       output_dir.mkdir(parents=True, exist_ok=True)
       
       wav_path = str(output_dir / f"{Path(audio_path).stem}.wav")
       
       cmd = [
           "ffmpeg", "-i", audio_path,
           "-ar", "16000", "-ac", "1",
           "-y", wav_path
       ]
       
       try:
           result = subprocess.run(cmd, capture_output=True, text=True, check=True)
       except subprocess.CalledProcessError as e:
           logger.error("ffmpeg failed: %s", e.stderr)
           raise RuntimeError(f"ffmpeg conversion failed: {e.stderr}") from e
       
       if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
           raise FileNotFoundError(f"WAV file not created or empty: {wav_path}")
       
       # Извлекаем длительность через ffprobe
       duration = _get_duration(wav_path)
       logger.info("Converted %s → %s (%.1fs)", audio_path, wav_path, duration)
       return wav_path, duration
   
   def _get_duration(path: str) -> float:
       result = subprocess.run(
           ["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path],
           capture_output=True, text=True, check=True
       )
       return float(result.stdout.strip())
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_audio.py`:
  - `test_convert_to_wav_creates_wav_file()` — создаёт тестовый MP3, конвертирует, проверяет .wav существует
  - `test_convert_to_wav_16khz_mono()` — проверяет параметры WAV через ffprobe (но это integration)
  - `test_convert_to_wav_nonexistent_file_raises()` — путь не существует → FileNotFoundError
  - `test_convert_to_wav_creates_output_dir()` — директория не существует → создаётся
  - `test_get_duration_returns_float()` — duration > 0
  - `test_convert_to_wav_empty_wav_raises()` — мокает subprocess, возвращает пустой файл → FileNotFoundError
  - `test_convert_to_wav_ffmpeg_error_raises()` — мокает subprocess, CalledProcessError → RuntimeError

---

## T3.2: Whisper transcription

**Длительность:** ~2 часа  
**Зависимости:** T3.1

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| WAV-файл (16kHz mono) | faster-whisper large-v3, beam_size=5, vad_filter | Транскрипция: список сегментов с speaker и текстом |

### Критерии приёмки
- [ ] `worker/transcription.py` — функция `transcribe_wav(wav_path: str) -> tuple[str, list[dict]]`
- [ ] Создаёт WhisperModel с параметрами: `device="cpu"`, `compute_type="int8"`, `beam_size=5`, `vad_filter=True`
- [ ] Для каждого сегмента: `speaker` (если доступен) + `text`
- [ ] Возвращает: (полный текст, список сегментов для детализации)
- [ ] Обработка ошибок: FileNotFoundError, RuntimeError при сбое Whisper

### Граничные случаи
- WAV-файл > 30 минут → Whisper может не справиться (large-v3 имеет лимит)
- Тишина > 3 секунд → vad_filter должен отфильтровать
- Многоязычная речь → language=None (автоопределение)
- Шумный фон → vad_filter + beam_size=5 должны улучшить результат
- Пустой файл → duration=0, возвращаем пустой текст
- Whisper не может загрузить модель → RuntimeError

### Пошаговый план
1. Создать `worker/transcription.py`:
   ```python
   import logging
   from faster_whisper import WhisperModel, download_model
   
   logger = logging.getLogger(__name__)
   
   _model_cache = {}
   
   def _get_model(model_name: str = "large-v3") -> WhisperModel:
       if model_name not in _model_cache:
           logger.info("Loading Whisper model: %s", model_name)
           _model_cache[model_name] = WhisperModel(
               model_name, device="cpu", compute_type="int8",
               download_root="/tmp/whisper_models"
           )
       return _model_cache[model_name]
   
   def transcribe_wav(wav_path: str, model_name: str = "large-v3") -> tuple[str, list[dict]]:
       if not wav_path.endswith(".wav"):
           raise ValueError(f"Expected .wav file, got: {wav_path}")
       
       model = _get_model(model_name)
       segments, info = model.transcribe(
           wav_path,
           beam_size=5,
           vad_filter=True,
           language=None,
           initial_prompt="Russian conversation"
       )
       
       duration = info.duration
       detected_lang = info.language or "unknown"
       logger.info(
           "Transcribed %.1fs of %s (detected: %s, confidence: %.2f)",
           duration, wav_path, detected_lang, info.language_probability
       )
       
       seg_list = []
       full_text = []
       for s in segments:
           speaker = s.speaker if hasattr(s, "speaker") and s.speaker is not None else "?"
           seg_list.append({
               "speaker": speaker,
               "start": s.start,
               "end": s.end,
               "text": s.text.strip()
           })
           full_text.append(f"Speaker {speaker}: {s.text}")
       
       return "\n".join(full_text), seg_list
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_transcription.py`:
  - `test_transcribe_wav_returns_text_and_segments()` — мокает WhisperModel, проверяет возвращаемые типы
  - `test_transcribe_wav_non_wav_raises()` — .mp3 файл → ValueError
  - `test_transcribe_wav_empty_segments()` — пустой segments → пустой текст
  - `test_transcribe_wav_speaker_extraction()` — сегмент с speaker=0 → "Speaker 0"
  - `test_transcribe_wav_no_speaker()` — сегмент без speaker → "Speaker ?"
  - `test_get_model_caches_model()` — вызов twice → один WhisperModel создан
  - `test_transcribe_wav_logs_detected_language()` — проверяет что логгер вызван с language

---

## T3.3: Task processing pipeline

**Длительность:** ~1.5 часа  
**Зависимости:** T3.1, T3.2

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Строка задачи `"room_id|audio_path"` | Pipeline: download check → convert → transcribe → return result | Результат транскрипции с метаданными |

### Критерии приёмки
- [ ] `worker/pipeline.py` — функция `process_transcription_task(task_str: str, config) -> dict`
- [ ] Парсит `task_str` → `room_id`, `audio_path`
- [ ] Проверяет существование `audio_path`
- [ ] Вызывает `convert_to_wav(audio_path, output_dir)`
- [ ] Вызывает `transcribe_wav(wav_path, model_name)`
- [ ] Возвращает dict: `{room_id, audio_path, transcript, segments, duration, wav_path}`
- [ ] Очистка временных WAV-файлов после завершения
- [ ] Логирование каждого шага

### Граничные случаи
- `audio_path` не существует → ValueError с понятным сообщением
- `task_str` не содержит `|` → ValueError
- `task_str` содержит больше одной `|` → ValueError
- Конвертация занимает > 10 минут → warning
- Транскрипция возвращает пустой текст → warning, но продолжать

### Пошаговый план
1. Создать `worker/pipeline.py`:
   ```python
   import os
   import logging
   from datetime import datetime
   from worker.audio import convert_to_wav
   from worker.transcription import transcribe_wav
   
   logger = logging.getLogger(__name__)
   
   def parse_task(task_str: str) -> tuple[str, str]:
       parts = task_str.split("|", 1)
       if len(parts) != 2:
           raise ValueError(f"Invalid task format, expected 'room_id|path': {task_str!r}")
       room_id, audio_path = parts
       if not room_id or not audio_path:
           raise ValueError(f"Task parts cannot be empty: {task_str!r}")
       return room_id, audio_path
   
   def process_transcription_task(task_str: str, config) -> dict:
       room_id, audio_path = parse_task(task_str)
       
       if not os.path.exists(audio_path):
           raise FileNotFoundError(f"Audio file not found: {audio_path}")
       
       logger.info("[%s] Starting transcription: %s", room_id, audio_path)
       
       wav_path, duration = convert_to_wav(audio_path, config.data_dir)
       transcript, segments = transcribe_wav(wav_path, config.whisper_model)
       
       logger.info("[%s] Transcription complete: %.1fs, %d chars", room_id, duration, len(transcript))
       
       return {
           "room_id": room_id,
           "audio_path": audio_path,
           "transcript": transcript,
           "segments": segments,
           "duration": duration,
           "wav_path": wav_path,
       }
   ```
2. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_pipeline.py`:
  - `test_parse_task_valid()` — "room1|/data/input/test.mp3" → ("room1", "/data/input/test.mp3")
  - `test_parse_task_missing_pipe_raises()` — "no-pipe-here" → ValueError
  - `test_parse_task_empty_room_raises()` — "|/path" → ValueError
  - `test_parse_task_empty_path_raises()` — "room|" → ValueError
  - `test_process_task_nonexistent_file_raises()` — несуществующий файл → FileNotFoundError
  - `test_process_task_returns_dict_with_keys()` — проверяет все ключи в результате
  - `test_process_task_logs_start_and_complete()` — проверяет логгер

---

## T3.4: Worker main loop

**Длительность:** ~1.5 часа  
**Зависимости:** T3.3

### Spec

| Input | Обработка | Output |
|-------|-----------|--------|
| Redis-очередь `transcription_queue` | Бесконечный blpop → process_transcription_task → publish результат | Воркер обрабатывает задачи до бесконечности, корректный shutdown |

### Критерии приёмки
- [ ] `worker/main.py` — функция `main()` с endless loop
- [ ] `redis_conn.blpop("transcription_queue")` — блокирующий poll
- [ ] Обработка ошибок: если задача упала → лог error, продолжить
- [ ] Graceful shutdown: обработка SIGTERM → очистка, выход
- [ ] Логирование: start, task_id, duration, error

### Граничные случаи
- Redis недоступен → retry с backoff (не crash)
- Очередь пуста → blpop блокирует (это ожидаемое поведение)
- Задача повисла > 30 минут → timeout (future)
- Несколько задач подряд → обрабатывать sequentially
- SIGTERM во время обработки → завершить текущую задачу, затем shutdown

### Пошаговый план
1. Создать `worker/main.py`:
   ```python
   import asyncio
   import signal
   import logging
   import redis
   from worker.config import WorkerConfig
   
   logger = logging.getLogger(__name__)
   
   shutdown_event = asyncio.Event()
   
   async def main():
       config = WorkerConfig()
       logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
       
       redis_conn = redis.Redis(host=config.redis_host, port=config.redis_port)
       
       def handle_signal():
           logger.info("Shutdown signal received")
           shutdown_event.set()
       
       loop = asyncio.get_running_loop()
       for sig in (signal.SIGTERM, signal.SIGINT):
           loop.add_signal_handler(sig, handle_signal)
       
       logger.info("Worker started. Redis: %s:%d, LLM: %s, Whisper: %s",
                   config.redis_host, config.redis_port, config.llm_api_url, config.whisper_model)
       
       while not shutdown_event.is_set():
           try:
               _, task_bytes = redis_conn.blpop("transcription_queue", timeout=5)
               if task_bytes is None:
                   continue
               
               task = task_bytes.decode()
               try:
                   from worker.pipeline import process_transcription_task
                   result = process_transcription_task(task, config)
                   # TODO: передать дальше (summarize → PDF → publish)
                   logger.info("Task processed: %s", task)
               except Exception as e:
                   logger.error("Task failed: %s — %s", task, e)
           except redis.ConnectionError as e:
               logger.error("Redis connection lost: %s. Retrying in 5s...", e)
               await asyncio.sleep(5)
       
       redis_conn.close()
       logger.info("Worker stopped")
   ```
2. Обновить `worker/worker.py`
3. Написать тесты

### Тесты (TDD)
- `tests/unit/test_worker_main.py`:
  - `test_main_starts_with_correct_log()` — проверяет логгер
  - `test_main_blpop_loop()` — мокает blpop, проверяет что вызывается для каждой задачи
  - `test_main_handles_redis_connection_error()` — ConnectionError → sleep(5), не crash
  - `test_main_handles_task_error_gracefully()` — исключение в process_task → лог error, продолжить
  - `test_signal_handler_sets_event()` — SIGTERM → shutdown_event.set()
  - `test_main_closes_redis_on_shutdown()` — redis_conn.close() вызван

---

## Интеграционный тест

### `tests/integration/test_worker_pipeline.py`
- `test_full_audio_pipeline()` — WAV-файл → convert → transcribe → результат не пустой
- `test_pipeline_with_real_ffmpeg()` — реальный ffmpeg, реальный WAV
