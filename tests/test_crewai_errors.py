"""Tests for :mod:`app.services.crewai.errors`."""

from src.app.services.crewai.errors import (
    DEFAULT_ERROR_MESSAGE,
    ERROR_MESSAGE_MAX_LENGTH,
    is_rate_limit_error,
    normalize_error_message,
)


class _RateLimitError(Exception):
    pass


class _ratelimit_exceeded(Exception):  # odd casing still trips the classifier
    pass


class TestIsRateLimitError:
    def test_matches_class_name_variants(self) -> None:
        assert is_rate_limit_error(_RateLimitError("boom"))
        assert is_rate_limit_error(_ratelimit_exceeded("boom"))

    def test_matches_message_substrings(self) -> None:
        assert is_rate_limit_error(Exception("429 Too Many Requests"))
        assert is_rate_limit_error(Exception("Provider returned: rate limit reached"))
        assert is_rate_limit_error(Exception("upstream error: rate_limit_exceeded"))

    def test_rejects_unrelated_errors(self) -> None:
        assert not is_rate_limit_error(Exception("TimeoutError"))
        assert not is_rate_limit_error(RuntimeError("model unavailable"))


class TestNormalizeErrorMessage:
    def test_keeps_a_single_line_within_the_column_limit(self) -> None:
        message = normalize_error_message(Exception("Something went wrong"))

        assert message == "Something went wrong"
        assert len(message) <= ERROR_MESSAGE_MAX_LENGTH

    def test_collapses_multi_line_traceback_to_first_line(self) -> None:
        error = Exception("first line\nsecond line\nthird line")

        assert normalize_error_message(error) == "first line"

    def test_truncates_overly_long_errors(self) -> None:
        long_text = "x" * (ERROR_MESSAGE_MAX_LENGTH + 500)
        message = normalize_error_message(Exception(long_text))

        assert len(message) == ERROR_MESSAGE_MAX_LENGTH

    def test_blank_exception_falls_back_to_default(self) -> None:
        assert normalize_error_message(Exception("   ")) == DEFAULT_ERROR_MESSAGE
