"""FastCRUD wrapper for the poets catalog.

The MVP only reads from this table — seeding is performed manually by
operators (see ``staged-workflow-handoff.md`` §9). Internal create /
update / delete schemas are still wired up so admin tooling can create
rows when the time comes.
"""

from __future__ import annotations

from fastcrud import FastCRUD
from pydantic import BaseModel, ConfigDict

from ..models.poet import Poet
from ..schemas.poet import PoetCardSchema


class _PoetCreateInternal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    era: str
    known_for: str
    style_markers: list[str] = []
    is_active: bool = True


class _PoetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    era: str | None = None
    known_for: str | None = None
    style_markers: list[str] | None = None
    is_active: bool | None = None


class _PoetUpdateInternal(_PoetUpdate):
    pass


class _PoetDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")


CRUDPoet = FastCRUD[Poet, _PoetCreateInternal, _PoetUpdate, _PoetUpdateInternal, _PoetDelete, PoetCardSchema]
crud_poets = CRUDPoet(Poet)
