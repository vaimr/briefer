"""Prometheus metrics for the worker."""

from prometheus_client import Counter, Gauge, Histogram

# --- Existing metrics ---
WORKER_TASKS_PROCESSED = Counter(
    "worker_tasks_processed_total", "Total tasks processed", ["status"]
)
WORKER_QUEUE_DEPTH = Gauge(
    "worker_queue_depth", "Current depth of transcription queue"
)
WORKER_WHISPER_LOADED = Gauge(
    "worker_whisper_loaded", "1 if Whisper model is loaded, 0 otherwise"
)

# --- Duration metric (replaces worker_task_duration_seconds) ---
WORKER_PROCESSING_DURATION = Histogram(
    "worker_processing_duration_seconds",
    "Worker task processing duration in seconds",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# --- Failure metric ---
WORKER_TASKS_FAILED = Counter(
    "worker_tasks_failed_total", "Total tasks failed", ["error_type"]
)
