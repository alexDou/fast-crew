"""Reusable Poet fixtures for crew and stage_1 tests.

The catalog is intentionally small (five poets) so individual tests
can spin up a believable picker-agent input set without seeding the
production-sized table. None of these rows are meant to land in
production: see ``staged-workflow-handoff.md`` §9 — operators populate
the live ``poets`` table separately.
"""

from __future__ import annotations

from src.app.schemas.poet import PoetCardSchema, PoetSelectorItemSchema

POET_FIXTURES: list[dict[str, object]] = [
    {
        "id": 11,
        "name": "Walt Whitman",
        "era": "19th century",
        "known_for": "American free verse",
        "style_markers": ["long line", "catalog imagery", "expansive voice"],
        "is_active": True,
    },
    {
        "id": 12,
        "name": "Emily Dickinson",
        "era": "19th century",
        "known_for": "Slant rhyme and compact lyric",
        "style_markers": ["dashes", "common metre", "metaphysical imagery"],
        "is_active": True,
    },
    {
        "id": 13,
        "name": "Matsuo Basho",
        "era": "17th century",
        "known_for": "Foundational haiku",
        "style_markers": ["seasonal kigo", "5-7-5 cadence", "stillness"],
        "is_active": True,
    },
    {
        "id": 14,
        "name": "Sylvia Plath",
        "era": "20th century",
        "known_for": "Confessional intensity",
        "style_markers": ["angular diction", "domestic gothic", "tight stanzas"],
        "is_active": True,
    },
    {
        "id": 15,
        "name": "Pablo Neruda",
        "era": "20th century",
        "known_for": "Sensual surrealism and odes",
        "style_markers": ["odic catalog", "earthy metaphor", "warm address"],
        "is_active": True,
    },
]


def poet_card_fixtures() -> list[PoetCardSchema]:
    """Return the fixtures as :class:`PoetCardSchema` instances."""
    return [
        PoetCardSchema(
            id=int(row["id"]),
            name=str(row["name"]),
            era=str(row["era"]),
            known_for=str(row["known_for"]),
            style_markers=list(row["style_markers"]),  # type: ignore[arg-type]
        )
        for row in POET_FIXTURES
    ]


def poet_selector_fixtures() -> list[PoetSelectorItemSchema]:
    """Return the fixtures as ``{id, name}`` picker inputs."""
    return [
        PoetSelectorItemSchema(id=int(row["id"]), name=str(row["name"]))
        for row in POET_FIXTURES
    ]


def poet_id_set() -> set[int]:
    """Return the fixture ID set used by validation tests."""
    return {int(row["id"]) for row in POET_FIXTURES}
