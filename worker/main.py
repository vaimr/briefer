"""Worker main loop — blpop → convert → transcribe → publish."""

import json
import logging
import signal
import sys
from pathlib import Path
from typing import List

import redis

from .audio_converter import AudioConverter
from .config import WorkerConfig
from .transcriber import Transcriber

logger = logging.getLogger(__name__)

QUEUE_NAME = "transcription_queue"
RESULTS_CHANNEL = "task_results"


class Worker:
    """Main worker that listens for tasks and processes them."""

    def __init__(
        self,
        config: WorkerConfig | None = None,
        converter: AudioConverter | None = None,
        transcriber: Transcriber | None = None,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self.config = config or WorkerConfig()
        self.converter = converter or AudioConverter()
        self.transcriber = transcriber or Transcriber(
            model_name=self.config.WHISPER_MODEL,
        )
        self.redis_client = redis_client or redis.Redis(
            host=self.config.REDIS_HOST,
            port=self.config.REDIS_PORT,
        )
        self.running = True

    def _handle_signal(self, signum: int, frame) -> None:
        logger.info("Signal %d received, shutting down…", signum)
        self.running = False

    def _process_task(self, key: str) -> None:
        room_id, message_id = key.split(":")
        input_path = Path(self.config.DATA_DIR) / room_id / f"{message_id}.mp3"

        wav_path = self.converter.convert(input_path)
        transcription = self.transcriber.transcribe(wav_path)

        self.redis_client.publish(
            RESULTS_CHANNEL,
            json.dumps({"key": key, "transcription": transcription}),
        )
        logger.info("Task %s completed", key)

    def run(self) -> None:
        """Run the worker main loop."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logger.info(
            "Worker started — listening on %s (host=%s, port=%d)",
            QUEUE_NAME,
            self.config.REDIS_HOST,
            self.config.REDIS_PORT,
        )

        while self.running:
            try:
                result = self.redis_client.blpop(QUEUE_NAME, timeout=30)
                if result is None:
                    # Timeout expired — check if we should stop
                    if not self.running:
                        break
                    continue

                key = result[1].decode()
                logger.info("Processing task: %s", key)
                self._process_task(key)

            except Exception as exc:
                logger.error("Task failed: %s", exc)
                continue

        logger.info("Worker stopped")


def main(
    running: List[bool] | None = None,
) -> None:
    """Entry point — creates a Worker and runs it.

    For testing, pass ``running = [True]`` and set ``running[0] = False``
    to stop the loop without relying on signals.
    """
    worker = Worker()
    if running is not None:
        worker.running = running[0]

        def _fake_handler(sig, frame) -> None:
            running[0] = False

        signal.signal(signal.SIGTERM, _fake_handler)
        signal.signal(signal.SIGINT, _fake_handler)

    worker.run()
