"""Health check endpoint для k8s readiness/liveness probes."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from nio import AsyncClient

from .config import BotConfig
from .metrics import BOT_MESSAGES_RECEIVED

HEALTH_STATE = {"matrix": "unknown", "redis": "unknown"}


def check_matrix(config: BotConfig) -> str:
    """Check Matrix connection.

    Given: a BotConfig with MATRIX_HOMESERVER and MATRIX_USER
    When: the homeserver is reachable
    Then: return 'healthy'
    When: the homeserver is unreachable
    Then: return 'unhealthy'
    """
    loop = asyncio.new_event_loop()
    try:
        client = AsyncClient(config.MATRIX_HOMESERVER, config.MATRIX_USER)
        if config.MATRIX_ACCESS_TOKEN:
            client.access_token = config.MATRIX_ACCESS_TOKEN
        loop.run_until_complete(client.sync_once(timeout=5000))
        return "healthy"
    except Exception:
        return "unhealthy"
    finally:
        loop.close()


def check_redis(config: BotConfig) -> str:
    """Check Redis connection.

    Given: a BotConfig with REDIS_HOST and REDIS_PORT
    When: Redis is reachable
    Then: return 'healthy'
    When: Redis is unreachable
    Then: return 'unhealthy'
    """
    import redis as redis_lib
    try:
        r = redis_lib.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT)
        r.ping()
        return "healthy"
    except Exception:
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

    settings: BotConfig = None  # type: ignore[assignment]

    def do_GET(self):
        if self.path == "/prometheus":
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
        elif self.path == "/health":
            HEALTH_STATE["redis"] = check_redis(self.settings)
            HEALTH_STATE["matrix"] = check_matrix(self.settings)

            status = _compute_status(HEALTH_STATE)
            http_status = 200 if status == "healthy" else 503
            body = json.dumps({
                "status": status,
                "checks": HEALTH_STATE
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


def start_http_server(config: BotConfig, port: int | None = None):
    """Start HTTP server for health/metrics in a daemon thread.

    Given: a BotConfig and optional port
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
