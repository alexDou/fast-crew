"""Shared enums reused across ORM models and Pydantic schemas."""

from enum import Enum


class PoemSourceStatus(str, Enum):
    """Canonical state machine for the staged poem workflow.

    The values double as the status string persisted on the
    ``poem_source.status`` column, so the ORM model and the response
    schemas can share a single source of truth.
    """

    PROCESSING = "processing"
    STAGE_1 = "stage_1"
    GENERATING = "generating"
    COMPLETE = "complete"
    ERROR = "error"

    @classmethod
    def values(cls) -> list[str]:
        """Return the raw status strings in declaration order."""
        return [member.value for member in cls]
