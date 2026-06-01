"""Health check endpoint для worker."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import redis
import requests

from .config import WorkerConfig
from .metrics import WORKER_WHISPER_LOADED

HEALTH_CHECKS: dict = {"redis": "unknown", "llm": "unknown", "whisper": "unknown"}


def check_redis(config: WorkerConfig) -> str:
    """Check Redis connection.

    Given: a WorkerConfig with REDIS_HOST and REDIS_PORT
    When: Redis is reachable
    Then: return 'healthy'
    When: Redis is unreachable
    Then: return 'unhealthy'
    """
    try:
        r = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT)
        r.ping()
        return "healthy"
    except Exception:
        return "unhealthy"


def check_llm(config: WorkerConfig) -> str:
    """Check LLM API availability.

    Given: a WorkerConfig with LLM_API_URL and LLM_MODEL_NAME
    When: the LLM API responds with 200
    Then: return 'healthy'
    When: the LLM API is unreachable
    Then: return 'unhealthy'
    """
    try:
        resp = requests.post(
            f"{config.LLM_API_URL}/chat/completions",
            json={
                "model": config.LLM_MODEL_NAME,
                "messages": [{"role": "user", "content": "ok"}],
                "max_tokens": 5,
            },
            timeout=5,
        )
        return "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception:
        return "unhealthy"


def check_whisper(config: WorkerConfig) -> str:
    """Check Whisper transcription engine availability.

    Given: a WorkerConfig with WHISPER_MODEL
    When: the whisper module can be imported (engine available)
    Then: return 'healthy'
    When: the whisper module cannot be imported
    Then: return 'unhealthy'
    """
    try:
        __import__("whisper")  # noqa: F401
        return "healthy"
    except ImportError:
        return "unhealthy"


def _compute_status(checks: dict) -> str:
    """Compute overall status from individual check results.

    Given: a dict of check_name -> 'healthy' | 'unhealthy'
    When: all checks are 'healthy'
    Then: return 'healthy'
    When: all checks are 'unhealthy'
    Then: return 'unhealthy'
    When: mixed results
    Then: return 'degraded'
    """
    statuses = list(checks.values())
    if all(s == "healthy" for s in statuses):
        return "healthy"
    if all(s == "unhealthy" for s in statuses):
        return "unhealthy"
    return "degraded"


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for /health and /prometheus endpoints."""

    settings: WorkerConfig = None  # type: ignore[assignment]

    def do_GET(self):
        if self.path == "/prometheus":
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
        elif self.path == "/health":
            HEALTH_CHECKS["redis"] = check_redis(self.settings)
            HEALTH_CHECKS["llm"] = check_llm(self.settings)
            HEALTH_CHECKS["whisper"] = check_whisper(self.settings)

            status = _compute_status(HEALTH_CHECKS)
            http_status = 200 if status == "healthy" else 503
            body = json.dumps({
                "status": status,
                "checks": HEALTH_CHECKS,
            })
            self.send_response(http_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass


def start_http_server(config: WorkerConfig, port: int | None = None):
    """Start HTTP server for health/metrics in a daemon thread.

    Given: a WorkerConfig and optional port
    When: port is not provided
    Then: use config.HEALTH_PORT
    When: port is provided
    Then: use the provided port
    """
    port = port or config.HEALTH_PORT
    HealthHandler.settings = config
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"  Health+Metrics HTTP server on port {port}")
