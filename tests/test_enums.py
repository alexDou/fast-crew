"""Tests for shared domain enums."""

from src.app.core.enums import PoemSourceStatus
from src.app.models.poem_source import PoemSourceStatus as ModelPoemSourceStatus
from src.app.schemas.poem_source import PoemSourceStatus as SchemaPoemSourceStatus


def test_models_and_schemas_share_the_same_enum_identity() -> None:
    """There must be exactly one PoemSourceStatus class across the codebase."""
    assert ModelPoemSourceStatus is PoemSourceStatus
    assert SchemaPoemSourceStatus is PoemSourceStatus


def test_status_values_match_frozen_staged_vocabulary() -> None:
    assert PoemSourceStatus.values() == [
        "processing",
        "stage_1",
        "generating",
        "complete",
        "error",
    ]


def test_status_members_are_string_backed() -> None:
    # str-enum members must compare equal to their raw string value so callers
    # that persist the enum value (and then compare against raw strings coming
    # from the database) do not drift.
    for member in PoemSourceStatus:
        assert isinstance(member.value, str)
        assert member == member.value
