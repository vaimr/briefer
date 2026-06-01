"""Tests for bot/health.py and worker/health.py health check endpoints.

TDD — Spec-Driven Development
Tests verify HTTP health endpoints for both bot and worker services.
Each test is isolated via mocking of external dependencies (Redis, Matrix, LLM, Whisper).
"""

import http.client
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from bot.config import BotConfig
from bot.health import HealthHandler as BotHealthHandler, check_matrix, check_redis
from worker.config import WorkerConfig
from worker.health import HealthHandler as WorkerHealthHandler, check_llm, check_redis as worker_check_redis, check_whisper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def bot_config():
    """Provide a minimal BotConfig for tests."""
    return BotConfig(
        MATRIX_HOMESERVER="https://matrix.example.com",
        MATRIX_USER="@bot:example.com",
        MATRIX_PASSWORD="pass",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        HEALTH_PORT=18081,
    )


@pytest.fixture()
def worker_config():
    """Provide a minimal WorkerConfig for tests."""
    return WorkerConfig(
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        LLM_API_URL="http://localhost:19001/v1",
        LLM_MODEL_NAME="test-model",
        WHISPER_MODEL="tiny",
        HEALTH_PORT=18082,
    )


def _start_health_server(handler_class, config, port):
    """Start a health HTTP server on a given port in a daemon thread.

    Returns the HTTPServer instance so it can be stopped later.
    """
    handler_class.settings = config
    server = http.server.HTTPServer(("127.0.0.1", port), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Give the server a moment to bind
    time.sleep(0.2)
    return server


def _health_get(port, path="/health", timeout=5):
    """Perform a GET request to the health server and return (status_code, parsed_json_or_none)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = None
        return resp.status, data
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bot health endpoint tests
# ---------------------------------------------------------------------------

class TestBotHealthEndpoint:
    """Tests for bot/health.py health endpoint."""

    def setup_method(self):
        """Reset bot HEALTH_STATE before each test to avoid cross-test pollution."""
        from bot import health as bot_health
        bot_health.HEALTH_STATE = {"matrix": "unknown", "redis": "unknown"}

    def test_health_returns_200_when_all_checks_pass(self, bot_config):
        """GET /health → 200 when all checks healthy."""
        with patch("bot.health.check_redis", return_value="healthy"), \
             patch("bot.health.check_matrix", return_value="healthy"):
            server = _start_health_server(BotHealthHandler, bot_config, 18083)
            try:
                status, data = _health_get(18083)
                assert status == 200
                assert data["status"] == "healthy"
            finally:
                server.shutdown()

    def test_health_returns_404_for_other_paths(self, bot_config):
        """GET /other → 404."""
        with patch("bot.health.check_redis", return_value="healthy"), \
             patch("bot.health.check_matrix", return_value="healthy"):
            server = _start_health_server(BotHealthHandler, bot_config, 18084)
            try:
                status, data = _health_get(18084, "/other")
                assert status == 404
            finally:
                server.shutdown()

    def test_health_returns_json(self, bot_config):
        """GET /health returns valid JSON with status and checks keys."""
        with patch("bot.health.check_redis", return_value="healthy"), \
             patch("bot.health.check_matrix", return_value="healthy"):
            server = _start_health_server(BotHealthHandler, bot_config, 18085)
            try:
                status, data = _health_get(18085)
                assert status == 200
                assert isinstance(data, dict)
                assert "status" in data
                assert "checks" in data
                assert data["status"] == "healthy"
            finally:
                server.shutdown()

    def test_health_healthy_when_all_checks_pass(self, bot_config):
        """All checks pass → status = 'healthy'."""
        with patch("bot.health.check_redis", return_value="healthy"), \
             patch("bot.health.check_matrix", return_value="healthy"):
            server = _start_health_server(BotHealthHandler, bot_config, 18086)
            try:
                status, data = _health_get(18086)
                assert status == 200
                assert data["status"] == "healthy"
            finally:
                server.shutdown()

    def test_health_degraded_when_one_check_fails(self, bot_config):
        """One check fails, one passes → status = 'degraded'."""
        with patch("bot.health.check_redis", return_value="unhealthy"), \
             patch("bot.health.check_matrix", return_value="healthy"):
            server = _start_health_server(BotHealthHandler, bot_config, 18087)
            try:
                status, data = _health_get(18087)
                assert status == 503
                assert data["status"] == "degraded"
            finally:
                server.shutdown()

    def test_health_unhealthy_when_all_checks_fail(self, bot_config):
        """All checks fail → status = 'unhealthy'."""
        with patch("bot.health.check_redis", return_value="unhealthy"), \
             patch("bot.health.check_matrix", return_value="unhealthy"):
            server = _start_health_server(BotHealthHandler, bot_config, 18088)
            try:
                status, data = _health_get(18088)
                assert status == 503
                assert data["status"] == "unhealthy"
            finally:
                server.shutdown()

    def test_health_bot_has_matrix_check(self, bot_config):
        """Bot /health response includes 'matrix' key in checks."""
        with patch("bot.health.check_redis", return_value="healthy"), \
             patch("bot.health.check_matrix", return_value="healthy"):
            server = _start_health_server(BotHealthHandler, bot_config, 18089)
            try:
                status, data = _health_get(18089)
                assert "matrix" in data["checks"]
            finally:
                server.shutdown()

    def test_health_bot_has_redis_check(self, bot_config):
        """Bot /health response includes 'redis' key in checks."""
        with patch("bot.health.check_redis", return_value="healthy"), \
             patch("bot.health.check_matrix", return_value="healthy"):
            server = _start_health_server(BotHealthHandler, bot_config, 18090)
            try:
                status, data = _health_get(18090)
                assert "redis" in data["checks"]
            finally:
                server.shutdown()


# ---------------------------------------------------------------------------
# Worker health endpoint tests
# ---------------------------------------------------------------------------

class TestWorkerHealthEndpoint:
    """Tests for worker/health.py health endpoint."""

    def _reset_worker_health(self):
        """Reset worker HEALTH_CHECKS to initial state."""
        from worker import health as worker_health
        worker_health.HEALTH_CHECKS = {"redis": "unknown", "llm": "unknown", "whisper": "unknown"}

    def test_health_returns_200_when_all_checks_pass(self, worker_config):
        """GET /health → 200 when all checks healthy."""
        with patch("worker.health.check_redis", return_value="healthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="healthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18091)
            try:
                status, data = _health_get(18091)
                assert status == 200
                assert data["status"] == "healthy"
            finally:
                server.shutdown()

    def test_health_returns_404_for_other_paths(self, worker_config):
        """GET /other → 404."""
        with patch("worker.health.check_redis", return_value="healthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="healthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18092)
            try:
                status, data = _health_get(18092, "/other")
                assert status == 404
            finally:
                server.shutdown()

    def test_health_returns_json(self, worker_config):
        """GET /health returns valid JSON with status and checks keys."""
        with patch("worker.health.check_redis", return_value="healthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="healthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18093)
            try:
                status, data = _health_get(18093)
                assert status == 200
                assert isinstance(data, dict)
                assert "status" in data
                assert "checks" in data
            finally:
                server.shutdown()

    def test_health_healthy_when_all_checks_pass(self, worker_config):
        """All checks pass → status = 'healthy'."""
        with patch("worker.health.check_redis", return_value="healthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="healthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18094)
            try:
                status, data = _health_get(18094)
                assert status == 200
                assert data["status"] == "healthy"
            finally:
                server.shutdown()

    def test_health_degraded_when_one_check_fails(self, worker_config):
        """One check fails, others pass → status = 'degraded'."""
        with patch("worker.health.check_redis", return_value="unhealthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="healthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18095)
            try:
                status, data = _health_get(18095)
                assert status == 503
                assert data["status"] == "degraded"
            finally:
                server.shutdown()

    def test_health_unhealthy_when_all_checks_fail(self, worker_config):
        """All checks fail → status = 'unhealthy'."""
        with patch("worker.health.check_redis", return_value="unhealthy"), \
             patch("worker.health.check_llm", return_value="unhealthy"), \
             patch("worker.health.check_whisper", return_value="unhealthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18096)
            try:
                status, data = _health_get(18096)
                assert status == 503
                assert data["status"] == "unhealthy"
            finally:
                server.shutdown()

    def test_health_worker_has_whisper_check(self, worker_config):
        """Worker /health response includes 'whisper' key in checks."""
        with patch("worker.health.check_redis", return_value="healthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="healthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18097)
            try:
                status, data = _health_get(18097)
                assert "whisper" in data["checks"]
            finally:
                server.shutdown()

    def test_health_worker_has_redis_check(self, worker_config):
        """Worker /health response includes 'redis' key in checks."""
        with patch("worker.health.check_redis", return_value="healthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="healthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18098)
            try:
                status, data = _health_get(18098)
                assert "redis" in data["checks"]
            finally:
                server.shutdown()

    def test_health_worker_has_llm_check(self, worker_config):
        """Worker /health response includes 'llm' key in checks."""
        with patch("worker.health.check_redis", return_value="healthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="healthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18099)
            try:
                status, data = _health_get(18099)
                assert "llm" in data["checks"]
            finally:
                server.shutdown()

    def test_health_degraded_when_whisper_fails(self, worker_config):
        """Whisper unavailable → status = 'degraded'."""
        with patch("worker.health.check_redis", return_value="healthy"), \
             patch("worker.health.check_llm", return_value="healthy"), \
             patch("worker.health.check_whisper", return_value="unhealthy"):
            self._reset_worker_health()
            server = _start_health_server(WorkerHealthHandler, worker_config, 18100)
            try:
                status, data = _health_get(18100)
                assert status == 503
                assert data["status"] == "degraded"
            finally:
                server.shutdown()


# ---------------------------------------------------------------------------
# Unit tests for check functions
# ---------------------------------------------------------------------------

class TestCheckFunctions:
    """Unit tests for individual health check functions."""

    def test_check_redis_healthy(self):
        """check_redis returns 'healthy' when Redis responds to ping."""
        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_cls = MagicMock(return_value=mock_instance)
        import sys
        original_redis = sys.modules.get("redis")
        sys.modules["redis"] = MagicMock(Redis=mock_redis_cls)
        try:
            config = BotConfig()
            result = check_redis(config)
            assert result == "healthy"
        finally:
            if original_redis is not None:
                sys.modules["redis"] = original_redis
            elif "redis" in sys.modules:
                del sys.modules["redis"]

    def test_check_redis_unhealthy(self):
        """check_redis returns 'unhealthy' when Redis ping fails."""
        import redis as redis_lib
        with patch.object(redis_lib, "Redis", side_effect=redis_lib.ConnectionError("fail")):
            config = BotConfig()
            result = check_redis(config)
            assert result == "unhealthy"

    def test_check_matrix_healthy(self):
        """check_matrix returns 'healthy' when sync succeeds."""
        mock_client = MagicMock()
        mock_client.sync_once = MagicMock()
        mock_loop = MagicMock()
        mock_loop.run_until_complete.return_value = None
        mock_loop.close = MagicMock()
        mock_asyncio = MagicMock()
        mock_asyncio.new_event_loop.return_value = mock_loop
        with patch("bot.health.AsyncClient", return_value=mock_client), \
             patch("bot.health.asyncio", mock_asyncio):
            config = BotConfig(MATRIX_HOMESERVER="https://example.com", MATRIX_USER="@bot:example.com")
            result = check_matrix(config)
            assert result == "healthy"

    def test_check_matrix_unhealthy(self):
        """check_matrix returns 'unhealthy' when sync raises."""
        mock_client = MagicMock()
        mock_client.sync_once = MagicMock(side_effect=Exception("network error"))
        mock_loop = MagicMock()
        mock_loop.run_until_complete = MagicMock(side_effect=Exception("network error"))
        mock_loop.close = MagicMock()
        mock_asyncio = MagicMock()
        mock_asyncio.new_event_loop.return_value = mock_loop
        with patch("bot.health.AsyncClient", return_value=mock_client), \
             patch("bot.health.asyncio", mock_asyncio):
            config = BotConfig(MATRIX_HOMESERVER="https://example.com", MATRIX_USER="@bot:example.com")
            result = check_matrix(config)
            assert result == "unhealthy"

    def test_check_whisper_healthy(self):
        """check_whisper returns 'healthy' when whisper module is importable."""
        import sys
        mock_whisper = MagicMock()
        sys.modules["whisper"] = mock_whisper
        try:
            config = WorkerConfig()
            result = check_whisper(config)
            assert result == "healthy"
        finally:
            sys.modules.pop("whisper", None)

    def test_check_whisper_unhealthy(self):
        """check_whisper returns 'unhealthy' when whisper module not found."""
        import sys
        sys.modules.pop("whisper", None)
        config = WorkerConfig()
        result = check_whisper(config)
        assert result == "unhealthy"

    def test_compute_status_all_healthy(self):
        """All healthy → 'healthy'."""
        from bot.health import _compute_status
        assert _compute_status({"redis": "healthy", "matrix": "healthy"}) == "healthy"

    def test_compute_status_all_unhealthy(self):
        """All unhealthy → 'unhealthy'."""
        from bot.health import _compute_status
        assert _compute_status({"redis": "unhealthy", "matrix": "unhealthy"}) == "unhealthy"

    def test_compute_status_mixed(self):
        """Mixed → 'degraded'."""
        from bot.health import _compute_status
        assert _compute_status({"redis": "healthy", "matrix": "unhealthy"}) == "degraded"
        assert _compute_status({"redis": "unhealthy", "matrix": "healthy"}) == "degraded"

    def test_compute_status_three_checks_all_healthy(self):
        """Three checks all healthy → 'healthy'."""
        from bot.health import _compute_status
        assert _compute_status({"redis": "healthy", "llm": "healthy", "whisper": "healthy"}) == "healthy"

    def test_compute_status_three_checks_all_unhealthy(self):
        """Three checks all unhealthy → 'unhealthy'."""
        from bot.health import _compute_status
        assert _compute_status({"redis": "unhealthy", "llm": "unhealthy", "whisper": "unhealthy"}) == "unhealthy"

    def test_compute_status_three_checks_mixed(self):
        """Three checks mixed → 'degraded'."""
        from bot.health import _compute_status
        assert _compute_status({"redis": "healthy", "llm": "unhealthy", "whisper": "healthy"}) == "degraded"
