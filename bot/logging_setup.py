"""JSON structured logging setup for the briefer bot."""

import json
import logging
import sys
from datetime import datetime, timezone

_VALID_LEVELS: set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines for stdout."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON-encoded log line."""
        entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": self._service,
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(service: str = "bot", level: str = "INFO") -> None:
    """Configure structured JSON logging for *service*.

    Parameters
    ----------
    service : str
        Service identifier included in every log record.
    level : str
        Logging level name. Must be one of
        DEBUG, INFO, WARNING, ERROR, CRITICAL.
        Empty string defaults to INFO.

    Raises
    ------
    ValueError
        If *level* is not a recognised log level.
    """
    if not level:
        level = "INFO"

    level_upper = level.upper()
    if level_upper not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}. "
            f"Must be one of {_VALID_LEVELS}"
        )

    logger = logging.getLogger(service)
    logger.setLevel(level_upper)

    # Avoid duplicate handlers on repeated calls.
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(service))
        logger.addHandler(handler)

    logger.info("Logging initialized: service=%s, level=%s", service, level_upper)
