"""Tests for worker/main.py — Worker main loop orchestration."""

import json
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worker.main import Worker, QUEUE_NAME, RESULTS_CHANNEL


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config():
    """Minimal WorkerConfig stub for tests."""
    cfg = MagicMock()
    cfg.REDIS_HOST = "localhost"
    cfg.REDIS_PORT = 6379
    cfg.WHISPER_MODEL = "tiny"
    cfg.DATA_DIR = "/tmp/briefer_test"
    return cfg


@pytest.fixture
def mock_redis():
    """Redis client stub."""
    client = MagicMock()
    client.blpop.return_value = None
    client.publish.return_value = 1
    return client


@pytest.fixture
def mock_converter():
    """AudioConverter stub."""
    converter = MagicMock()
    converter.convert.return_value = Path("/tmp/out.wav")
    return converter


@pytest.fixture
def mock_transcriber():
    """Transcriber stub."""
    transcriber = MagicMock()
    transcriber.transcribe.return_value = {
        "text": "Hello world",
        "segments": [],
        "duration": 3.0,
        "language": "en",
    }
    return transcriber


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_worker(config, redis, converter, transcriber):
    """Create a Worker with all dependencies injected (no real constructors)."""
    return Worker(
        config=config,
        converter=converter,
        transcriber=transcriber,
        redis_client=redis,
    )


def _stop_worker(worker):
    """Helper: stop the worker loop after one blpop call."""
    def _stop(queue, timeout=30):
        worker.running = False
        return None
    return _stop


def _blpop_seq(tasks, worker):
    """Callable side_effect: yield *tasks* then return None and stop worker.

    Parameters
    ----------
    tasks : list of tuple
        Each element is ``(b"queue_name", b"key")`` that ``blpop`` should return.
    worker : Worker
        The worker instance whose ``running`` flag will be set to ``False``
        after all tasks have been yielded.
    """
    _idx = [0]  # mutable index to survive closures

    def _fn(queue, timeout=30):
        if _idx[0] < len(tasks):
            _idx[0] += 1
            return tasks[_idx[0] - 1]
        worker.running = False
        return None

    return _fn


def _run_worker(worker, blpop_side_effect=None):
    """Run worker.run() with signal.signal patched.

    Uses blpop side_effect to control loop termination:
    - If blpop_side_effect is a list, yield each item then return None
    - If blpop_side_effect is callable, use it directly
    - If blpop_side_effect is None, blpop returns None and worker.running is
      set to False after the first blpop call so the loop exits.
    """
    if blpop_side_effect is None:
        blpop_side_effect = _stop_worker(worker)

    worker.running = True
    mock_redis = worker.redis_client
    mock_redis.blpop.side_effect = blpop_side_effect

    with patch("worker.main.signal.signal"):
        worker.run()


# ---------------------------------------------------------------------------
# Test: Worker.__init__
# ---------------------------------------------------------------------------


class TestWorkerInit:
    def test_init_running_flag_true(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        assert worker.running is True

    def test_init_uses_passed_config(self):
        cfg = MagicMock()
        worker = _make_worker(cfg, MagicMock(), MagicMock(), MagicMock())
        assert worker.config is cfg

    def test_init_uses_passed_converter(self):
        conv = MagicMock()
        worker = _make_worker(MagicMock(), MagicMock(), conv, MagicMock())
        assert worker.converter is conv

    def test_init_uses_passed_transcriber(self):
        trans = MagicMock()
        worker = _make_worker(MagicMock(), MagicMock(), MagicMock(), trans)
        assert worker.transcriber is trans

    def test_init_uses_passed_redis_client(self):
        rds = MagicMock()
        worker = _make_worker(MagicMock(), rds, MagicMock(), MagicMock())
        assert worker.redis_client is rds


# ---------------------------------------------------------------------------
# Test: Worker._handle_signal
# ---------------------------------------------------------------------------


class TestWorkerHandleSignal:
    def test_handle_signal_sets_running_false(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        worker.running = True
        worker._handle_signal(signal.SIGTERM, None)
        assert worker.running is False

    def test_handle_signal_logs_info(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        with patch("worker.main.logger") as mock_logger:
            worker._handle_signal(signal.SIGINT, None)
            mock_logger.info.assert_called_once()
            assert "Signal" in str(mock_logger.info.call_args)


# ---------------------------------------------------------------------------
# Test: Worker._process_task — normal processing
# ---------------------------------------------------------------------------


class TestProcessTask:
    def _make(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        return _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)

    def test_process_task_calls_converter(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = self._make(mock_config, mock_redis, mock_converter, mock_transcriber)
        worker._process_task("room1:msg42")
        mock_converter.convert.assert_called_once_with(
            Path("/tmp/briefer_test/room1/msg42.mp3")
        )

    def test_process_task_calls_transcriber(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = self._make(mock_config, mock_redis, mock_converter, mock_transcriber)
        worker._process_task("room1:msg42")
        mock_transcriber.transcribe.assert_called_once_with(Path("/tmp/out.wav"))

    def test_process_task_publishes_result(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = self._make(mock_config, mock_redis, mock_converter, mock_transcriber)
        worker._process_task("room1:msg42")
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == RESULTS_CHANNEL
        published = json.loads(call_args[0][1])
        assert published["key"] == "room1:msg42"
        assert published["transcription"]["text"] == "Hello world"

    def test_process_task_key_format(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = self._make(mock_config, mock_redis, mock_converter, mock_transcriber)
        worker._process_task("meeting-abc:12345")
        mock_converter.convert.assert_called_once_with(
            Path("/tmp/briefer_test/meeting-abc/12345.mp3")
        )

    def test_process_task_includes_transcription_in_publish(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = self._make(mock_config, mock_redis, mock_converter, mock_transcriber)
        worker._process_task("room1:msg42")
        published = json.loads(mock_redis.publish.call_args[0][1])
        assert "transcription" in published
        assert published["transcription"]["duration"] == 3.0
        assert published["transcription"]["language"] == "en"


# ---------------------------------------------------------------------------
# Test: Worker._process_task — error handling (errors propagate, caught by run())
# ---------------------------------------------------------------------------


class TestProcessTaskErrorHandling:
    def _make(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        return _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)

    def test_converter_error_no_publish(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        mock_converter.convert.side_effect = FileNotFoundError("No such file")
        worker = self._make(mock_config, mock_redis, mock_converter, mock_transcriber)
        with pytest.raises(FileNotFoundError):
            worker._process_task("room1:msg42")
        mock_redis.publish.assert_not_called()

    def test_transcriber_error_no_publish(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        mock_transcriber.transcribe.side_effect = RuntimeError("Whisper failed")
        mock_converter.convert.return_value = Path("/tmp/out.wav")
        worker = self._make(mock_config, mock_redis, mock_converter, mock_transcriber)
        with pytest.raises(RuntimeError):
            worker._process_task("room1:msg42")
        mock_redis.publish.assert_not_called()

    def test_invalid_key_format_raises_value_error(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = self._make(mock_config, mock_redis, mock_converter, mock_transcriber)
        with pytest.raises(ValueError):
            worker._process_task("invalid-key-no-colon")


# ---------------------------------------------------------------------------
# Test: Worker.run — main loop
# ---------------------------------------------------------------------------


class TestWorkerRun:
    def test_run_exits_when_running_is_false(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        worker.running = False
        mock_redis.blpop.return_value = None

        with patch("worker.main.signal.signal"):
            worker.run()

        mock_redis.blpop.assert_not_called()

    def test_run_calls_signal_handlers(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)

        with patch("worker.main.signal.signal") as mock_signal:
            mock_redis.blpop.side_effect = _stop_worker(worker)
            worker.run()

        assert mock_signal.call_count == 2
        calls = mock_signal.call_args_list
        signals_called = [c[0][0] for c in calls]
        assert signal.SIGTERM in signals_called
        assert signal.SIGINT in signals_called

    def test_run_continues_on_blpop_timeout(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        mock_redis.blpop.return_value = None

        with patch("worker.main.signal.signal"):
            _run_worker(worker)

        assert mock_redis.blpop.call_count >= 1

    def test_run_exits_on_signal_during_blpop(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        mock_redis.blpop.return_value = None

        with patch("worker.main.signal.signal"):
            worker._handle_signal(signal.SIGTERM, None)
            worker.run()

        assert worker.running is False

    def test_run_processes_single_task(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        mock_redis.blpop.side_effect = _blpop_seq(
            [(b"transcription_queue", b"room1:msg42")],
            worker,
        )

        with patch("worker.main.signal.signal"):
            worker.run()

        mock_converter.convert.assert_called_once()
        mock_transcriber.transcribe.assert_called_once()
        mock_redis.publish.assert_called_once()

    def test_run_continues_after_error(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        _call_count = [0]

        def _convert(path):
            if _call_count[0] == 0:
                _call_count[0] += 1
                raise FileNotFoundError("No file")
            return Path("/tmp/out.wav")

        mock_converter_fail = MagicMock()
        mock_converter_fail.convert.side_effect = _convert

        mock_redis_ok = MagicMock()
        mock_redis_ok.publish.return_value = 1

        worker = Worker(
            config=mock_config,
            converter=mock_converter_fail,
            transcriber=mock_transcriber,
            redis_client=mock_redis_ok,
        )

        worker.redis_client.blpop.side_effect = _blpop_seq(
            [
                (b"transcription_queue", b"room1:fail"),
                (b"transcription_queue", b"room2:ok"),
            ],
            worker,
        )

        with patch("worker.main.signal.signal"):
            worker.run()

        assert mock_redis_ok.publish.call_count == 1

    def test_run_processes_multiple_tasks(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        mock_redis.blpop.side_effect = _blpop_seq(
            [
                (b"transcription_queue", b"room1:msg1"),
                (b"transcription_queue", b"room2:msg2"),
                (b"transcription_queue", b"room3:msg3"),
            ],
            worker,
        )

        with patch("worker.main.signal.signal"):
            worker.run()

        assert mock_converter.convert.call_count == 3
        assert mock_transcriber.transcribe.call_count == 3
        assert mock_redis.publish.call_count == 3

    def test_run_checks_running_after_blpop_timeout(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)
        mock_redis.blpop.return_value = None

        with patch("worker.main.signal.signal"):
            worker._handle_signal(signal.SIGTERM, None)
            worker.run()

        assert worker.running is False

    def test_run_logs_start_and_stop(self, mock_config, mock_redis, mock_converter, mock_transcriber):
        worker = _make_worker(mock_config, mock_redis, mock_converter, mock_transcriber)

        with (
            patch("worker.main.signal.signal"),
            patch("worker.main.logger") as mock_logger,
        ):
            _run_worker(worker)

        start_calls = [c for c in mock_logger.info.call_args_list if "started" in str(c)]
        assert len(start_calls) >= 1
        stop_calls = [c for c in mock_logger.info.call_args_list if "stopped" in str(c)]
        assert len(stop_calls) >= 1


# ---------------------------------------------------------------------------
# Test: main() entry point
# ---------------------------------------------------------------------------


class TestEntryPoint:
    def test_main_creates_worker(self):
        from worker.main import main

        with patch("worker.main.Worker") as MockWorker:
            mock_instance = MagicMock()
            MockWorker.return_value = mock_instance
            main()
        MockWorker.assert_called_once()
        mock_instance.run.assert_called_once()

    def test_main_calls_run_once(self):
        from worker.main import main

        with patch("worker.main.Worker") as MockWorker:
            mock_instance = MagicMock()
            MockWorker.return_value = mock_instance
            main()
        assert mock_instance.run.call_count == 1

    def test_main_with_running_flag_true(self):
        from worker.main import main

        running = [True]
        with patch("worker.main.Worker") as MockWorker:
            mock_instance = MagicMock()
            MockWorker.return_value = mock_instance
            main(running=running)

        assert mock_instance.running is True

    def test_main_with_running_flag_false(self):
        from worker.main import main

        running = [False]
        with patch("worker.main.Worker") as MockWorker:
            mock_instance = MagicMock()
            MockWorker.return_value = mock_instance
            main(running=running)

        assert mock_instance.running is False

    def test_main_without_running_flag(self):
        from worker.main import main

        with patch("worker.main.Worker") as MockWorker:
            mock_instance = MagicMock()
            mock_instance.running = True
            MockWorker.return_value = mock_instance
            main()

        assert mock_instance.running is True


# ---------------------------------------------------------------------------
# Test: Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_queue_name(self):
        assert QUEUE_NAME == "transcription_queue"

    def test_results_channel(self):
        assert RESULTS_CHANNEL == "task_results"
