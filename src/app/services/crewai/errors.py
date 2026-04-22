"""Error classification and normalization helpers for the CrewAI service."""

from __future__ import annotations

INDISTINCT_CONTENT_MESSAGE = "indistinct content"
ERROR_MESSAGE_MAX_LENGTH = 1000
DEFAULT_ERROR_MESSAGE = "Poem generation failed"


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True if ``exc`` looks like a 429 / rate-limit response.

    LiteLLM raises ``litellm.exceptions.RateLimitError`` but CrewAI may
    wrap it, so we check both the exception class name and the message
    for the well-known signatures.
    """
    exc_name = type(exc).__name__
    exc_str = str(exc).lower()
    if "ratelimit" in exc_name.lower() or exc_name == "RateLimitError":
        return True
    if "429" in exc_str or "rate limit" in exc_str or "rate_limit" in exc_str:
        return True
    return False


def normalize_error_message(exc: Exception) -> str:
    """Produce a durable, single-line error message for ``poem_source.error_message``.

    The message is truncated to :data:`ERROR_MESSAGE_MAX_LENGTH` so it
    always fits in the database column even for verbose upstream errors.
    """
    message = str(exc).strip()
    if not message:
        return DEFAULT_ERROR_MESSAGE
    return message.splitlines()[0][:ERROR_MESSAGE_MAX_LENGTH]
