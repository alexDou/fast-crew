"""Shared helpers for staged workflow API tests."""

from unittest.mock import Mock


def scalar_result(value):
    """Build a mock SQLAlchemy result for ``scalar_one_or_none``."""
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result
