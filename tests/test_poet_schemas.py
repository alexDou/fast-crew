"""Schema-level tests for the curated poets catalog.

These tests run without a database — they validate the Pydantic
contracts that flow between the picker agent, the API, and the UI.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.app.schemas.poet import PoetCardSchema, PoetSelectorItemSchema


class TestPoetSelectorItemSchema:
    def test_round_trip_from_orm_attributes(self) -> None:
        orm_like = SimpleNamespace(id=11, name="Walt Whitman")

        schema = PoetSelectorItemSchema.model_validate(orm_like)

        assert schema.id == 11
        assert schema.name == "Walt Whitman"

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValueError):
            PoetSelectorItemSchema.model_validate(
                {"id": 11, "name": "Walt Whitman", "era": "19th century"}
            )

    def test_requires_non_empty_name(self) -> None:
        with pytest.raises(ValueError):
            PoetSelectorItemSchema.model_validate({"id": 1, "name": ""})


class TestPoetCardSchema:
    def test_round_trip_from_orm_attributes(self) -> None:
        orm_like = SimpleNamespace(
            id=12,
            name="Emily Dickinson",
            era="19th century",
            known_for="Slant rhyme",
            style_markers=["dashes", "compact lyric"],
        )

        schema = PoetCardSchema.model_validate(orm_like)

        assert schema.id == 12
        assert schema.name == "Emily Dickinson"
        assert schema.era == "19th century"
        assert schema.known_for == "Slant rhyme"
        assert schema.style_markers == ["dashes", "compact lyric"]

    def test_default_style_markers_is_empty_list(self) -> None:
        schema = PoetCardSchema.model_validate(
            {"id": 1, "name": "n", "era": "e", "known_for": "k"}
        )

        assert schema.style_markers == []

    def test_serialises_to_camel_safe_dict(self) -> None:
        schema = PoetCardSchema(
            id=11,
            name="Walt Whitman",
            era="19th century",
            known_for="Free verse",
            style_markers=["long line"],
        )

        payload = schema.model_dump()
        assert payload == {
            "id": 11,
            "name": "Walt Whitman",
            "era": "19th century",
            "known_for": "Free verse",
            "style_markers": ["long line"],
        }
