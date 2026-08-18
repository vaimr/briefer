"""Главный entry point бота."""

import argparse
import asyncio
import json
import logging
import signal
import sys
from io import BytesIO
from pathlib import Path
from typing import Optional

import redis

from nio import InviteMemberEvent, RoomMessageAudio, RoomMessageFile, RoomMessageText, SyncError

from .config import BotConfig
from .health import start_http_server
from .logging_setup import setup_logging
from .matrix_client import (
    create_client,
    get_audio_event_type,
    handle_audio_message,
    handle_non_audio_message,
    load_help_text,
)
from .metrics import BOT_QUEUE_DEPTH
from .result_listener import ResultListener

logger = logging.getLogger("bot")


async def result_listener(client, pubsub) -> None:
    """Listen to Redis pub/sub channel ``task_results`` and deliver results."""
    while True:
        try:
            message = await asyncio.get_event_loop().run_in_executor(
                None, lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
            )
            if message and message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                except json.JSONDecodeError as exc:
                    logger.error("JSON parse error: %s", exc)
                    continue

                if "task_id" not in data:
                    logger.error("Message missing task_id: %s", message["data"])
                    continue

                try:
                    await _deliver_result(client, pubsub, data)
                except Exception as exc:
                    logger.error("Callback error: %s", exc)
        except Exception as exc:
            logger.error("Result listener error: %s", exc)
            await asyncio.sleep(1)


async def _deliver_result(client, pubsub, data) -> None:
    """Deliver transcription result to the Matrix room."""
    room_id = data.get("room_id")
    task_id = data.get("task_id")
    original_filename = data.get("original_filename", "audio")
    event_id = data.get("event_id")
    transcript_md = data.get("transcript_md")
    transcript_pdf = data.get("transcript_pdf")
    summary_md = data.get("summary_md")
    summary_pdf = data.get("summary_pdf")
    risk_files = data.get("risk_files", [])

    base = original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename

    if not all([room_id, task_id, transcript_md, transcript_pdf, summary_md, summary_pdf]):
        logger.error("Invalid result data: %s", data)
        return

    try:
        import os

        files_to_send = [
            (transcript_md, f"{base}_transcript.md", "text/markdown"),
            (transcript_pdf, f"{base}_transcript.pdf", "application/pdf"),
            (summary_md, f"{base}_summary.md", "text/markdown"),
            (summary_pdf, f"{base}_summary.pdf", "application/pdf"),
        ]
        for path, name, mime in files_to_send:
            if not os.path.exists(path):
                raise FileNotFoundError(f"{name} not found: {path}")
            if os.path.getsize(path) == 0:
                raise ValueError(f"{name} is empty: {path}")

        file_data_map = {}
        for path, name, mime in files_to_send:
            file_data_map[path] = Path(path).read_bytes()

        for path, name, mime in files_to_send:
            file_data = file_data_map[path]
            resp, _ = await client.upload(BytesIO(file_data), content_type=mime, filename=name)
            mxc_uri = resp.content_uri

            msg = {
                "msgtype": "m.file",
                "body": name,
                "url": mxc_uri,
                "info": {
                    "mimetype": mime,
                },
            }
            if event_id:
                msg["m.relates_to"] = {
                    "rel_type": "m.reference",
                    "in_reply_to": {"event_id": event_id},
                }
            resp = await client.room_send(
                room_id,
                "m.room.message",
                msg,
            )
            logger.info("Sent %s to %s: %s (resp=%s)", name, room_id, mxc_uri, type(resp).__name__)

        for risk_path in risk_files:
            if not os.path.exists(risk_path):
                logger.warning("Risk file not found: %s", risk_path)
                continue
            risk_data = Path(risk_path).read_bytes()
            resp, _ = await client.upload(BytesIO(risk_data), content_type="application/pdf", filename=f"{base}_risk_alert.pdf")
            mxc_uri = resp.content_uri
            msg = {
                "msgtype": "m.file",
                "body": f"{base}_risk_alert.pdf",
                "url": mxc_uri,
                "info": {"mimetype": "application/pdf"},
            }
            if event_id:
                msg["m.relates_to"] = {
                    "rel_type": "m.reference",
                    "in_reply_to": {"event_id": event_id},
                }
            await client.room_send(
                room_id,
                "m.room.message",
                msg,
            )
            logger.info("Sent risk_alert.pdf to %s: %s", room_id, mxc_uri)

        msg = {"msgtype": "m.notice", "body": "Результаты готовы!"}
        if event_id:
            msg["m.relates_to"] = {
                "rel_type": "m.reference",
                "in_reply_to": {"event_id": event_id},
            }
        await client.room_send(
            room_id,
            "m.room.message",
            msg,
        )
        logger.info("Results delivered to %s", room_id)

        ResultListener.publish_cleanup(settings.REDIS_HOST, settings.REDIS_PORT, task_id)
    except Exception as exc:
        logger.error("Failed to deliver results to %s: %s", room_id, exc)
        try:
            await client.room_send(
                room_id,
                "m.room.message",
                {"msgtype": "m.notice", "body": f"Ошибка при отправке результатов: {exc}"},
            )
        except Exception:
            logger.error("Could not notify user about delivery failure")

# ---------------------------------------------------------------------------
# Global shutdown event
# ---------------------------------------------------------------------------

shutdown_event: asyncio.Event = asyncio.Event()

result_listener_task: Optional[asyncio.Task[None]] = None

settings = BotConfig()


async def _handle_shutdown(sig: signal.Signals) -> None:
    """Handle SIGTERM/SIGINT: set shutdown event and wait for consumer.

    Idempotent — only the first signal triggers the full shutdown sequence.
    Subsequent signals are ignored (shutdown already in progress).
    """
    if shutdown_event.is_set():
        logger.info("Shutdown already in progress, ignoring %s", sig.name)
        return

    logger.info("Shutting down...")
    shutdown_event.set()

    global result_listener_task
    task = result_listener_task
    result_listener_task = None

    if task is not None and not task.done():
        try:
            await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Result listener task timed out")
        except Exception:
            logger.exception("Error waiting for result listener task")


async def main():
    """Запуск бота: Matrix client + Redis pub/sub + HTTP health/metrics.

    Given: BotConfig with all required fields
    When: the bot starts
    Then: validate_required() is called, Redis and Matrix clients are created,
          health/metrics server is started, signal handlers are registered,
          and sync_forever begins
    When: SIGTERM or SIGINT is received
    Then: shutdown_event is set and sync_forever exits gracefully
    When: an error occurs in sync_forever
    Then: error is logged, redis_client is closed, and bot stops cleanly
    """
    # Валидация обязательных полей перед стартом
    settings.validate_required()

    setup_logging(service="bot", level=settings.LOG_LEVEL)
    logger.info("Bot starting up")

    # Подключение к Redis для очередей
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=False,
    )

    client = await create_client(settings)
    logger.info("Matrix client created: %s", settings.MATRIX_HOMESERVER)

    help_text = load_help_text(settings.HELP_TEXT_FILE)
    logger.info("Help text loaded: %d chars", len(help_text))

    # Подписка на аудио сообщения
    bot_user_id = client.user_id
    async def callback(room, event):
        try:
            sender = event.sender
            # Compare by localpart + domain (strip @) to handle both @user:server and user:server formats
            bot_user = settings.MATRIX_USER.lstrip("@")
            sender_clean = sender.lstrip("@")
            if sender_clean == bot_user:
                logger.debug("Skipping own message: %s sender=%s", type(event).__name__, sender)
                return

            room_id = room.room_id
            message_id = event.source.get("event_id", "unknown")
            logger.info("Received event: room=%s, type=%s, message_id=%s, sender=%s", room_id, type(event).__name__, message_id, sender)

            # Skip non-audio files (pdf, md) sent by bot
            if isinstance(event, RoomMessageFile) and sender_clean == bot_user:
                return

            if get_audio_event_type(event):
                logger.info(
                    "Processing audio message: room_id=%s, message_id=%s",
                    room_id,
                    message_id,
                )
                try:
                    await handle_audio_message(
                        client, room_id, event, "/data/input",
                        lambda task: redis_client.rpush("transcription_queue", task),
                    )
                    logger.info("Audio validated: %s", room_id)
                    logger.info("Pushed to queue: %s", room_id)
                except Exception as exc:
                    logger.error("Error processing message: %s", exc)
                    try:
                        await client.room_send(
                            room_id,
                            "m.room.message",
                            {"msgtype": "m.notice", "body": f"Ошибка: {exc}"},
                        )
                    except Exception:
                        logger.exception("Failed to send error notification")
            else:
                logger.info("Non-audio message received: room_id=%s", room_id)
                await handle_non_audio_message(client, room_id, help_text)
        except Exception:
            logger.exception("Unhandled callback error")

    client.add_event_callback(callback, (RoomMessageAudio, RoomMessageFile, RoomMessageText))
    logger.info("Event callback registered: RoomMessageAudio, RoomMessageFile, RoomMessageText")

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    # Auto-join DM rooms
    async def invite_handler(room, event):
        room_id = room.room_id
        logger.info("Received invite to room: %s", room_id)
        await client.join(room_id)
        logger.info("Joined room: %s", room_id)

    # ------------------------------------------------------------------
    # Response callback: log sync state for diagnostics
    # ------------------------------------------------------------------
    _sync_count = 0

    async def sync_state_callback(response):
        nonlocal _sync_count
        if hasattr(response, "next_batch"):
            _sync_count += 1
            rooms_join = len(getattr(response, "rooms", None).join or {})
            rooms_invite = len(getattr(response, "rooms", None).invite or {})
            logger.info(
                "Sync #%d: next_batch=%s, rooms.join=%d, rooms.invite=%d",
                _sync_count,
                getattr(response, "next_batch", "N/A")[:32] if getattr(response, "next_batch", None) else "N/A",
                rooms_join,
                rooms_invite,
            )
            if rooms_join == 0 and _sync_count > 2:
                known_rooms = list(client.rooms.keys()) if hasattr(client, "rooms") else []
                logger.warning(
                    "Sync returned 0 joined rooms after %d syncs — bot may have stale sync state or invalid token. Known rooms: %s",
                    _sync_count,
                    known_rooms,
                )

    client.add_response_callback(sync_state_callback)
    logger.info("Sync state callback registered")

    client.add_event_callback(invite_handler, (InviteMemberEvent,))
    logger.info("Invite callback registered for auto-join DM rooms")

    sync_error_count = 0

    async def response_callback(response):
        nonlocal sync_error_count
        if isinstance(response, SyncError):
            sync_error_count += 1
            errcode = getattr(response, "status_code", None) or "N/A"
            error_msg = getattr(response, "message", str(response)) or "unknown"
            retry_after = getattr(response, "retry_after_ms", None)
            soft_logout = getattr(response, "soft_logout", False)
            logger.error(
                "Matrix sync returned SyncError (count=%d): errcode=%s, error=%s, "
                "retry_after_ms=%s, soft_logout=%s",
                sync_error_count,
                errcode,
                error_msg,
                retry_after,
                soft_logout,
            )
            transport = getattr(response, "transport_response", None)
            if transport is not None:
                logger.error(
                    "Raw transport: status=%s, url=%s, body=%r",
                    getattr(transport, "status", "N/A"),
                    getattr(transport, "url", "N/A"),
                    getattr(transport, "_body", getattr(transport, "body", "N/A")),
                )

    client.add_response_callback(response_callback)
    logger.info("SyncError response callback registered")

    # Подписка на результаты
    pubsub = redis_client.pubsub()
    pubsub.subscribe("task_results")
    global result_listener_task
    result_listener_task = asyncio.create_task(result_listener(client, pubsub))

    # Подписка на ошибки (отдельный поток)
    import threading
    error_thread = threading.Thread(
        target=ResultListener.listen_for_errors,
        args=(client, settings.REDIS_HOST, settings.REDIS_PORT),
        daemon=True,
    )
    error_thread.start()
    logger.info("Error listener thread started")

    # Health + metrics
    start_http_server(settings)

    # --- Signal handlers (must be after loop is running) ---
    pending_shutdown: Optional[asyncio.Task[None]] = None

    def _signal_wrapper(sig: signal.Signals) -> None:
        nonlocal pending_shutdown
        pending_shutdown = asyncio.ensure_future(_handle_shutdown(sig))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_wrapper, sig)

    # Основной цикл: sync_forever with SyncError retry
    sync_attempt = 0

    try:
        logger.info("Starting sync loop...")
        while not shutdown_event.is_set():
            sync_attempt += 1
            try:
                logger.info("Sync loop iteration #%d", sync_attempt)
                await client.sync_forever(timeout=30000)
                # sync_forever only exits on CancelledError or exception
                break
            except asyncio.CancelledError:
                logger.info("Sync loop cancelled")
                break
            except Exception as exc:
                logger.error("sync_forever exception (attempt #%d): %s", sync_attempt, exc)
                if shutdown_event.is_set():
                    break
                await asyncio.sleep(5)
    except Exception as exc:
        logger.error("sync_forever error: %s", exc)
    finally:
        # Wait for any pending shutdown handler to complete
        if pending_shutdown is not None and not pending_shutdown.done():
            try:
                await asyncio.wait_for(pending_shutdown, timeout=35)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("Shutdown handler did not complete in time")
        logger.info("Bot shutting down")
        redis_client.close()
        logger.info("Bot stopped")


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser.

    Currently supports --help flag only.
    Extensible for future CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Briefer Matrix bot for audio transcription",
    )
    return parser


if __name__ == "__main__":
    _build_parser()
    asyncio.run(main())
