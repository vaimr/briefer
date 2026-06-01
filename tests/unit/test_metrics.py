"""Unit tests for bot/worker Prometheus metrics."""

import pytest
from prometheus_client import CollectorRegistry, generate_latest


def _fresh_registry(*collectors):
    """Return a fresh CollectorRegistry with the given collectors registered."""
    reg = CollectorRegistry()
    for c in collectors:
        reg.register(c)
    return reg


# ---------------------------------------------------------------------------
# Counter: BOT_TASKS_PROCESSED
# ---------------------------------------------------------------------------


class TestCounterTasksProcessedIncrements:
    """Test that BOT_TASKS_PROCESSED counter increments correctly."""

    def test_increments_on_success(self):
        """Counter increments when status=success."""
        from bot.metrics import BOT_TASKS_PROCESSED

        BOT_TASKS_PROCESSED.labels(status="success").inc()
        value = BOT_TASKS_PROCESSED._metrics[("success",)]._value.get()
        assert value >= 1.0

    def test_increments_on_error(self):
        """Counter increments when status=error."""
        from bot.metrics import BOT_TASKS_PROCESSED

        BOT_TASKS_PROCESSED.labels(status="error").inc()
        value = BOT_TASKS_PROCESSED._metrics[("error",)]._value.get()
        assert value >= 1.0

    def test_increments_by_custom_amount(self):
        """Counter increments by a custom amount."""
        from bot.metrics import BOT_TASKS_PROCESSED

        before = BOT_TASKS_PROCESSED._metrics[("success",)]._value.get()
        BOT_TASKS_PROCESSED.labels(status="success").inc(5)
        after = BOT_TASKS_PROCESSED._metrics[("success",)]._value.get()
        assert after == before + 5.0


# ---------------------------------------------------------------------------
# Counter: BOT_TASKS_FAILED / WORKER_TASKS_FAILED
# ---------------------------------------------------------------------------


class TestCounterTasksFailedIncrements:
    """Test that BOT_TASKS_FAILED counter increments correctly."""

    def test_increments_with_error_type(self):
        """Counter increments with error_type label."""
        from bot.metrics import BOT_TASKS_FAILED

        BOT_TASKS_FAILED.labels(error_type="timeout").inc()
        value = BOT_TASKS_FAILED._metrics[("timeout",)]._value.get()
        assert value >= 1.0

    def test_tracks_multiple_error_types(self):
        """Counter tracks separate counts per error_type."""
        from bot.metrics import BOT_TASKS_FAILED

        BOT_TASKS_FAILED.labels(error_type="timeout").inc()
        BOT_TASKS_FAILED.labels(error_type="api_error").inc()

        timeout_val = BOT_TASKS_FAILED._metrics[("timeout",)]._value.get()
        api_val = BOT_TASKS_FAILED._metrics[("api_error",)]._value.get()
        assert timeout_val >= 1.0
        assert api_val >= 1.0

    def test_worker_failed_increments(self):
        """Worker counter increments with error_type label."""
        from worker.metrics import WORKER_TASKS_FAILED

        WORKER_TASKS_FAILED.labels(error_type="transcription_failed").inc()
        value = WORKER_TASKS_FAILED._metrics.get(("transcription_failed",))
        assert value is not None
        assert value._value.get() >= 1.0


# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------


class TestHistogramRecordsDuration:
    """Test that processing duration histograms record correctly."""

    def test_bot_histogram_records_duration(self):
        """Bot histogram records duration via context manager."""
        from bot.metrics import BOT_PROCESSING_DURATION

        with BOT_PROCESSING_DURATION.time():
            pass  # measure elapsed time
        samples = BOT_PROCESSING_DURATION._samples()
        count_samples = [s for s in samples if s.name == "_count"]
        assert len(count_samples) == 1
        assert count_samples[0].value >= 1.0

    def test_bot_histogram_observes_value(self):
        """Bot histogram records observed duration value."""
        from bot.metrics import BOT_PROCESSING_DURATION

        BOT_PROCESSING_DURATION.observe(0.5)
        samples = BOT_PROCESSING_DURATION._samples()
        sum_samples = [s for s in samples if s.name == "_sum"]
        assert len(sum_samples) == 1
        assert sum_samples[0].value >= 0.5

    def test_worker_histogram_records_duration(self):
        """Worker histogram records duration via context manager."""
        from worker.metrics import WORKER_PROCESSING_DURATION

        with WORKER_PROCESSING_DURATION.time():
            pass  # measure elapsed time
        samples = WORKER_PROCESSING_DURATION._samples()
        count_samples = [s for s in samples if s.name == "_count"]
        assert len(count_samples) == 1
        assert count_samples[0].value >= 1.0

    def test_histogram_bucket_labels_exist(self):
        """Histogram exposes le labels for all configured buckets."""
        from bot.metrics import BOT_PROCESSING_DURATION

        BOT_PROCESSING_DURATION.observe(0.05)
        BOT_PROCESSING_DURATION.observe(0.3)
        BOT_PROCESSING_DURATION.observe(2.0)
        BOT_PROCESSING_DURATION.observe(10.0)
        BOT_PROCESSING_DURATION.observe(45.0)
        BOT_PROCESSING_DURATION.observe(120.0)

        samples = BOT_PROCESSING_DURATION._samples()
        bucket_samples = {s.labels["le"]: s for s in samples if s.name == "_bucket"}

        assert "0.1" in bucket_samples
        assert "0.5" in bucket_samples
        assert "1.0" in bucket_samples
        assert "5.0" in bucket_samples
        assert "10.0" in bucket_samples
        assert "30.0" in bucket_samples
        assert "60.0" in bucket_samples
        assert "+Inf" in bucket_samples

        # Verify cumulative bucket counts
        assert bucket_samples["0.1"].value >= 1.0  # 0.05 and 0.3
        assert bucket_samples["0.5"].value >= 2.0  # 0.05, 0.3
        assert bucket_samples["5.0"].value >= 3.0  # 0.05, 0.3, 2.0
        assert bucket_samples["10.0"].value >= 4.0  # 0.05, 0.3, 2.0, 10.0
        assert bucket_samples["30.0"].value >= 4.0
        assert bucket_samples["60.0"].value >= 4.0
        assert bucket_samples["+Inf"].value >= 6.0


# ---------------------------------------------------------------------------
# Prometheus exposition format
# ---------------------------------------------------------------------------


class TestMetricsFormatPrometheus:
    """Test that metrics are exported in Prometheus exposition format."""

    def test_bot_metrics_export_format(self):
        """Bot metrics output is in valid Prometheus exposition format."""
        from bot.metrics import (
            BOT_PROCESSING_DURATION,
            BOT_TASKS_FAILED,
            BOT_TASKS_PROCESSED,
        )

        reg = _fresh_registry(BOT_TASKS_PROCESSED, BOT_TASKS_FAILED, BOT_PROCESSING_DURATION)
        BOT_TASKS_PROCESSED.labels(status="success").inc()
        BOT_TASKS_FAILED.labels(error_type="timeout").inc()
        BOT_PROCESSING_DURATION.observe(0.3)

        output = generate_latest(reg).decode("utf-8")

        assert "bot_tasks_processed_total" in output
        assert 'bot_tasks_processed_total{status="success"}' in output
        assert "bot_tasks_failed_total" in output
        assert 'bot_tasks_failed_total{error_type="timeout"}' in output
        assert "bot_processing_duration_seconds" in output

    def test_worker_metrics_export_format(self):
        """Worker metrics output is in valid Prometheus exposition format."""
        from worker.metrics import (
            WORKER_PROCESSING_DURATION,
            WORKER_TASKS_FAILED,
            WORKER_TASKS_PROCESSED,
        )

        reg = _fresh_registry(WORKER_TASKS_PROCESSED, WORKER_TASKS_FAILED, WORKER_PROCESSING_DURATION)
        WORKER_TASKS_PROCESSED.labels(status="success").inc()
        WORKER_TASKS_FAILED.labels(error_type="whisper_error").inc()
        WORKER_PROCESSING_DURATION.observe(5.0)

        output = generate_latest(reg).decode("utf-8")

        assert "worker_tasks_processed_total" in output
        assert 'worker_tasks_processed_total{status="success"}' in output
        assert "worker_tasks_failed_total" in output
        assert 'worker_tasks_failed_total{error_type="whisper_error"}' in output
        assert "worker_processing_duration_seconds" in output

    def test_counter_name_format(self):
        """Counter names follow Prometheus naming conventions (end with _total)."""
        from bot.metrics import (
            BOT_TASKS_FAILED,
            BOT_TASKS_PROCESSED,
        )
        from worker.metrics import WORKER_TASKS_FAILED as WTF, WORKER_TASKS_PROCESSED as WTP

        reg = _fresh_registry(BOT_TASKS_PROCESSED, BOT_TASKS_FAILED, WTP, WTF)
        BOT_TASKS_PROCESSED.labels(status="success").inc()
        BOT_TASKS_FAILED.labels(error_type="timeout").inc()

        output = generate_latest(reg).decode("utf-8")

        assert "bot_tasks_processed_total" in output
        assert "bot_tasks_failed_total" in output
        assert "worker_tasks_processed_total" in output
        assert "worker_tasks_failed_total" in output

    def test_histogram_buckets_configured(self):
        """Histogram uses configured bucket boundaries in exposition format."""
        from bot.metrics import BOT_PROCESSING_DURATION

        reg = _fresh_registry(BOT_PROCESSING_DURATION)
        BOT_PROCESSING_DURATION.observe(0.3)

        output = generate_latest(reg).decode("utf-8")

        assert 'le="0.1"' in output
        assert 'le="0.5"' in output
        assert 'le="1.0"' in output
        assert 'le="5.0"' in output
        assert 'le="10.0"' in output
        assert 'le="30.0"' in output
        assert 'le="60.0"' in output
        assert 'le="+Inf"' in output

    def test_histogram_sum_and_count_in_output(self):
        """Histogram exports _sum and _count samples."""
        from bot.metrics import BOT_PROCESSING_DURATION

        reg = _fresh_registry(BOT_PROCESSING_DURATION)
        BOT_PROCESSING_DURATION.observe(1.5)

        output = generate_latest(reg).decode("utf-8")

        assert "bot_processing_duration_seconds_sum" in output
        assert "bot_processing_duration_seconds_count" in output
