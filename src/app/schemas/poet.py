"""Pydantic schemas for the curated poets catalog.

Two narrow projections are exported:

* ``PoetCardSchema`` is what the UI renders inside the stage_1 cards
  (and what the server persists on ``poem_source.poet_candidates`` so
  URL-resume can rehydrate without re-running the picker).
* ``PoetSelectorItemSchema`` is the minimal payload that the picker
  agent receives — only ``id`` + ``name``. The stage-2 writer may receive
  the full card payload for the one poet the user selected.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["PoetCardSchema", "PoetSelectorItemSchema"]


class PoetSelectorItemSchema(BaseModel):
    """The pruned ``{id, name}`` view sent to the poet picker agent."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    name: Annotated[str, Field(min_length=1, max_length=200)]


class PoetCardSchema(BaseModel):
    """The card payload the UI renders for each candidate poet."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    name: Annotated[str, Field(min_length=1, max_length=200)]
    era: Annotated[str, Field(min_length=1, max_length=120)]
    known_for: Annotated[str, Field(min_length=1, max_length=300)]
    style_markers: list[str] = Field(default_factory=list)
