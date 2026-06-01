"""Prometheus metrics for the bot."""

from prometheus_client import Counter, Gauge, Histogram

# --- Existing message metrics ---
BOT_MESSAGES_RECEIVED = Counter(
    "bot_messages_received_total", "Total messages received", ["type"]
)
BOT_MESSAGES_PROCESSED = Counter(
    "bot_messages_processed_total", "Total messages processed", ["status"]
)
BOT_QUEUE_DEPTH = Gauge(
    "bot_queue_depth", "Current depth of transcription queue"
)

# --- Task metrics ---
BOT_TASKS_PROCESSED = Counter(
    "bot_tasks_processed_total", "Total bot tasks processed", ["status"]
)
BOT_TASKS_FAILED = Counter(
    "bot_tasks_failed_total", "Total bot tasks failed", ["error_type"]
)
BOT_PROCESSING_DURATION = Histogram(
    "bot_processing_duration_seconds",
    "Bot task processing duration in seconds",
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
)
