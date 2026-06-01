"""Briefer bot exceptions."""


class BotError(Exception):
    """Base exception for bot errors."""


class MatrixAuthError(BotError):
    """Failed to authenticate with Matrix."""


class MatrixSendError(BotError):
    """Failed to send message to Matrix."""


class MatrixDownloadError(BotError):
    """Failed to download media from Matrix."""


class RedisError(BotError):
    """Redis connection error."""


class TaskQueueError(RedisError):
    """Failed to push task to queue."""


class ResultDeliveryError(BotError):
    """Failed to deliver result to Matrix room."""
