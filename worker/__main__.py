"""Главный entry point воркера."""

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import os
import shutil
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from redis import ConnectionError as RedisConnectionError
from redis import Redis

from .config import WorkerConfig
from .health import start_http_server
from .llm_engine import LLMAPI
from .metrics import WORKER_QUEUE_DEPTH, WORKER_PROCESSING_DURATION, WORKER_TASKS_PROCESSED, WORKER_WHISPER_LOADED
from .pdf_generator import generate_pdf
from .whisper_engine import WhisperEngine

logger = logging.getLogger("worker")

QUEUE_NAME = "transcription_queue"
CLEANUP_CHANNEL = "task_cleanup"
RESULTS_DIR = Path("/tmp/results")

settings = WorkerConfig()


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines for stdout."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "worker",
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for worker."""
    if not level:
        level = "INFO"
    logger.setLevel(level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)


def get_date() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


@contextmanager
def task_timer():
    with WORKER_PROCESSING_DURATION.time():
        yield


def process_task_sync(task_str: str, whisper: WhisperEngine, llm: LLMAPI, redis_conn, loop: asyncio.AbstractEventLoop) -> None:
    parts = task_str.split("|", 3)
    room_id = parts[0]
    audio_path = parts[1]
    original_filename = parts[2] if len(parts) > 2 else None
    event_id = parts[3] if len(parts) > 3 else None

    logger.info("Processing: %s for %s", audio_path, room_id)

    transcript, duration = whisper.transcribe(audio_path)
    logger.info("Transcribed: %.0fs", duration)

    summary, risks = _summarize_and_risks_sync(llm, transcript)

    logger.info("Summarized: %d chars", len(summary))
    logger.info("Risks: %s", risks.get("risk_level", "unknown"))

    if not summary or not summary.strip():
        logger.warning("Empty summary from LLM, using placeholder")
        summary = "Нет данных для саммари"

    task_id = hashlib.sha256(audio_path.encode()).hexdigest()[:16]
    task_dir = RESULTS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Task directory: %s", task_dir)

    # Extract base name from original filename, fallback to audio_path stem
    if original_filename:
        base = os.path.splitext(original_filename)[0]
    else:
        base = os.path.splitext(os.path.basename(audio_path))[0]

    transcript_md = (
        f"# Полная транскрипция\n\n"
        f"**Дата:** {get_date()}\n"
        f"**Длительность:** {duration:.0f} сек\n\n"
        f"{transcript}"
    )
    summary_md = f"# Саммари встречи\n\n{summary}"

    transcript_md_path = task_dir / f"{base}_transcript.md"
    summary_md_path = task_dir / f"{base}_summary.md"
    transcript_md_path.write_text(transcript_md, encoding="utf-8")
    summary_md_path.write_text(summary_md, encoding="utf-8")
    logger.info("Markdown files: %s, %s", transcript_md_path, summary_md_path)

    transcript_pdf = generate_pdf(transcript_md, f"{task_dir}/{base}_transcript")
    summary_pdf = generate_pdf(summary_md, f"{task_dir}/{base}_summary")
    logger.info("PDF files: %s, %s", transcript_pdf, summary_pdf)

    risk_files = []
    if risks.get("is_risky", False):
        risk_md = (
            f"# Warning: dangerous discussions detected\n\n"
            f"**Risk level:** {risks.get('risk_level', 'unknown').upper()}\n\n"
            "## Identified categories\n\n"
        )
        for cat in risks.get("categories", []):
            risk_md += f"- {cat}\n"
        risk_md += "\n## Details\n\n"
        for detail in risks.get("details", []):
            risk_md += f"### {detail.get('category', 'unknown')}\n\n"
            risk_md += f"**Quote:** {detail.get('quote', '')}\n\n"
            risk_md += f"**Description:** {detail.get('description', '')}\n\n"
        risk_md += f"\n**Summary:** {risks.get('summary', '')}\n"
        risk_pdf = generate_pdf(risk_md, f"{task_dir}/risk_alert")
        risk_files.append(str(risk_pdf))
        logger.info("Risk alert generated: %s", risk_pdf)

    all_files = [str(transcript_pdf), str(summary_pdf)] + risk_files
    message = {
        "task_id": task_id,
        "room_id": room_id,
        "original_filename": original_filename or base,
        "event_id": event_id,
        "transcript_md": str(transcript_md_path),
        "transcript_pdf": str(transcript_pdf),
        "summary_md": str(summary_md_path),
        "summary_pdf": str(summary_pdf),
        "risk_files": risk_files,
        "timestamp": datetime.now().isoformat(),
    }
    redis_conn.publish("task_results", json.dumps(message))
    logger.info("Results published: %d files to %s", len(all_files), task_dir)


def publish_error(redis_conn, room_id: str, task_id: str, error: str) -> None:
    """Publish a processing error to the error channel."""
    message = {
        "task_id": task_id,
        "room_id": room_id,
        "error": error,
        "timestamp": datetime.now().isoformat(),
    }
    redis_conn.publish("task_errors", json.dumps(message))
    logger.error("Error published for task %s: %s", task_id, error)


def _summarize_and_risks_sync(llm: LLMAPI, transcript: str) -> tuple:
    logger.info("Starting LLM summarize + risk check")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        summary_future = executor.submit(llm.summarize, transcript)
        risks_future = executor.submit(llm.check_risks, transcript)
        summary = summary_future.result()
        risks = risks_future.result()
    logger.info("LLM tasks completed")
    return summary, risks


def dequeue_task(redis_conn: Redis) -> Optional[Tuple[str, str]]:
    """Pop the next task from the Redis queue.

    Given: a Redis connection
    When: a task is available
    Then: the value is split on ``|`` and returned as ``(room_id, audio_path)``
    When: no task is available within 5 seconds
    Then: ``None`` is returned
    When: the Redis server is unreachable
    Then: ``ConnectionError`` is raised

    Args:
        redis_conn: Active Redis client instance.

    Returns:
        A ``(room_id, audio_path)`` tuple, or ``None`` on timeout.

    Raises:
        ConnectionError: If the Redis server is unreachable.
    """
    try:
        result = redis_conn.blpop(QUEUE_NAME, timeout=5)
    except RedisConnectionError as exc:
        raise ConnectionError(f"Redis connection failed: {exc}") from exc

    if result is None:
        return None

    _queue_name, value = result
    task_str = value.decode() if isinstance(value, bytes) else str(value)

    parts = task_str.split("|", 1)
    if len(parts) != 2:
        logger.error("Malformed queue entry: %s", task_str)
        raise ValueError(f"Malformed queue entry: {task_str!r}")

    room_id, audio_path = parts
    logger.info("Dequeued task: room_id=%s, audio_path=%s", room_id, audio_path)
    return room_id, audio_path


def cleanup_listener(redis_host: str, redis_port: int) -> None:
    """Listen for cleanup requests and delete task directories."""
    _running = True

    def _handle_signal(signum, frame):
        nonlocal _running
        _running = False

    try:
        import signal
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
    except ValueError:
        pass

    r = Redis(host=redis_host, port=redis_port, decode_responses=True)
    pubsub = r.pubsub()
    pubsub.subscribe(CLEANUP_CHANNEL)

    logger.info("Cleanup listener started on channel %s", CLEANUP_CHANNEL)

    try:
        while _running:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    task_id = data.get("task_id")
                    if task_id:
                        task_dir = RESULTS_DIR / task_id
                        if task_dir.exists():
                            shutil.rmtree(task_dir)
                            logger.info("Cleaned up: %s", task_dir)
                        else:
                            logger.warning("Cleanup target not found: %s", task_dir)
                except json.JSONDecodeError as exc:
                    logger.error("Cleanup JSON parse error: %s", exc)
                except Exception as exc:
                    logger.error("Cleanup error: %s", exc, exc_info=True)
    finally:
        pubsub.unsubscribe(CLEANUP_CHANNEL)
        pubsub.close()


def main():
    setup_logging(level=settings.LOG_LEVEL)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info("Worker started")
    logger.info("  Redis: %s:%s", settings.REDIS_HOST, settings.REDIS_PORT)
    logger.info("  LLM: %s", settings.LLM_API_URL)
    logger.info("  Whisper model: %s", settings.WHISPER_MODEL)

    start_http_server(settings)

    whisper = WhisperEngine(settings.WHISPER_MODEL)
    WORKER_WHISPER_LOADED.set(1)
    llm = LLMAPI(settings.LLM_API_URL, settings.LLM_MODEL_NAME)

    import time

    def get_redis():
        return Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            socket_connect_timeout=5,
            socket_timeout=30,
            socket_keepalive=True,
        )

    redis_conn = get_redis()

    cleanup_thread = threading.Thread(
        target=cleanup_listener,
        args=(settings.REDIS_HOST, settings.REDIS_PORT),
        daemon=True,
    )
    cleanup_thread.start()

    while True:
        try:
            result = redis_conn.blpop("transcription_queue", timeout=5)
            if result is None:
                continue
            _, task = result
            try:
                with task_timer():
                    process_task_sync(
                        task.decode(), whisper, llm, redis_conn, loop,
                    )
                    WORKER_TASKS_PROCESSED.labels(status="success").inc()
            except Exception as e:
                logger.error("Error processing task: %s", e, exc_info=True)
                WORKER_TASKS_PROCESSED.labels(status="error").inc()
                try:
                    task_str = task.decode()
                    room_id = task_str.split("|", 1)[0] if "|" in task_str else "unknown"
                    task_id = hashlib.sha256(task_str.split("|", 1)[1].encode()).hexdigest()[:16] if "|" in task_str else "unknown"
                    publish_error(redis_conn, room_id, task_id, str(e))
                except Exception:
                    logger.error("Failed to publish error notification")
        except (ConnectionError, TimeoutError, redis.exceptions.RedisError) as e:
            logger.error("Redis connection error: %s. Reconnecting in 5s...", e)
            WORKER_TASKS_PROCESSED.labels(status="error").inc()
            try:
                redis_conn.close()
            except Exception:
                pass
            redis_conn = get_redis()
            time.sleep(5)


if __name__ == "__main__":
    main()
