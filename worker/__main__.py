"""Главный entry point воркера."""

import asyncio
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime
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

QUEUE_NAME = "transcription_queue"
CLEANUP_CHANNEL = "task_cleanup"
RESULTS_DIR = Path("/tmp/results")

settings = WorkerConfig()


def get_date() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


@contextmanager
def task_timer():
    with WORKER_PROCESSING_DURATION.time():
        yield


def process_task_sync(task_str: str, whisper: WhisperEngine, llm: LLMAPI, redis_conn, loop: asyncio.AbstractEventLoop) -> None:
    room_id, audio_path = task_str.split("|", 1)
    base_name = os.path.splitext(audio_path)[0]

    print(f"[{datetime.now()}] Processing: {audio_path} for {room_id}")

    transcript, duration = whisper.transcribe(audio_path)
    print(f"  Transcribed: {duration:.0f}s")

    summary, risks = asyncio.run_coroutine_threadsafe(
        _async_summarize_and_risks(llm, transcript),
        loop,
    ).result()

    print(f"  Summarized: {len(summary)} chars")
    print(f"  Risks: {risks.get('risk_level', 'unknown')}")

    # Генерируем уникальный task_id из audio_path
    task_id = hashlib.sha256(audio_path.encode()).hexdigest()[:16]
    task_dir = RESULTS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    # Markdown файлы
    transcript_md = (
        f"# Полная транскрипция\n\n"
        f"**Дата:** {get_date()}\n"
        f"**Длительность:** {duration:.0f} сек\n\n"
        f"{transcript}"
    )
    summary_md = f"# Саммари встречи\n\n{summary}"

    transcript_md_path = task_dir / "transcript.md"
    summary_md_path = task_dir / "summary.md"
    transcript_md_path.write_text(transcript_md, encoding="utf-8")
    summary_md_path.write_text(summary_md, encoding="utf-8")
    print(f"  Markdown files: {transcript_md_path}, {summary_md_path}")

    # PDF файлы
    transcript_pdf = generate_pdf(transcript_md, f"{task_dir}/transcript")
    summary_pdf = generate_pdf(summary_md, f"{task_dir}/summary")

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
        print(f"  Risk alert generated: {risk_pdf}")

    all_files = [str(transcript_pdf), str(summary_pdf)] + risk_files
    message = {
        "task_id": task_id,
        "room_id": room_id,
        "transcript_md": str(transcript_md_path),
        "transcript_pdf": str(transcript_pdf),
        "summary_md": str(summary_md_path),
        "summary_pdf": str(summary_pdf),
        "risk_files": risk_files,
        "timestamp": datetime.now().isoformat(),
    }
    redis_conn.publish("task_results", json.dumps(message))
    print(f"  Results published: {len(all_files)} files to {task_dir}")


async def _async_summarize_and_risks(llm: LLMAPI, transcript: str) -> tuple:
    summary, risks = await asyncio.gather(
        asyncio.get_event_loop().run_in_executor(None, llm.summarize, transcript),
        asyncio.get_event_loop().run_in_executor(None, llm.check_risks, transcript),
    )
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
        print(f"Malformed queue entry: {task_str!r}")
        raise ValueError(f"Malformed queue entry: {task_str!r}")

    room_id, audio_path = parts
    print(f"Dequeued task: room_id={room_id}, audio_path={audio_path}")
    return room_id, audio_path


def cleanup_listener(redis_host: str, redis_port: int) -> None:
    import json
    import signal
    import threading

    _running = True

    def _handle_signal(signum, frame):
        nonlocal _running
        _running = False

    try:
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
    except ValueError:
        pass

    import redis

    r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    pubsub = r.pubsub()
    pubsub.subscribe(CLEANUP_CHANNEL)

    print(f"Cleanup listener started on channel {CLEANUP_CHANNEL}")

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
                            import shutil
                            shutil.rmtree(task_dir)
                            print(f"Cleaned up: {task_dir}")
                        else:
                            print(f"Cleanup target not found: {task_dir}")
                except json.JSONDecodeError as exc:
                    print(f"Cleanup JSON parse error: {exc}")
                except Exception as exc:
                    print(f"Cleanup error: {exc}")
    finally:
        pubsub.unsubscribe(CLEANUP_CHANNEL)
        pubsub.close()


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    print(f"[{datetime.now()}] Worker started")
    print(f"  Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print(f"  LLM: {settings.LLM_API_URL}")
    print(f"  Whisper model: {settings.WHISPER_MODEL}")

    start_http_server(settings)

    whisper = WhisperEngine(settings.WHISPER_MODEL)
    WORKER_WHISPER_LOADED.set(1)
    llm = LLMAPI(settings.LLM_API_URL, settings.LLM_MODEL_NAME)

    import redis
    import time

    def get_redis():
        return redis.Redis(
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
                print(f"Error processing task: {e}")
                WORKER_TASKS_PROCESSED.labels(status="error").inc()
        except (ConnectionError, TimeoutError, redis.exceptions.RedisError) as e:
            print(f"Redis connection error: {e}. Reconnecting in 5s...")
            WORKER_TASKS_PROCESSED.labels(status="error").inc()
            try:
                redis_conn.close()
            except Exception:
                pass
            redis_conn = get_redis()
            time.sleep(5)


if __name__ == "__main__":
    main()
