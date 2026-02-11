import os
from enum import Enum

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..core.schemas import PersistentDeletion, TimestampSchema, UUIDSchema


class PoemSourceStatus(str, Enum):
    """Status of poem generation processing."""
    PROCESSING = "processing"
    SUCCESS = "success"
    ERROR = "error"


base_media_path = os.path.join(os.getcwd(), "media/")


class PoemSourceBase(BaseModel):
    pass


class PoemSource(TimestampSchema, PoemSourceBase, UUIDSchema, PersistentDeletion):
    user_id: int
    media_path: Annotated[
        str | None,
        Field(examples=[base_media_path], default=None),
    ]
    enhance: Annotated[
        str | None,
        Field(default=None, max_length=500),
    ]
    status: Annotated[
        str,
        Field(default="processing"),
    ]


class PoemSourceRead(BaseModel):
    id: int
    media_path: Annotated[
        str | None,
        Field(examples=[base_media_path], default=None),
    ]
    enhance: Annotated[
        str | None,
        Field(default=None),
    ]
    status: Annotated[
        str,
        Field(default="processing"),
    ]
    user_id: int
    created_at: datetime


class PoemSourceCreate(PoemSourceBase):
    model_config = ConfigDict(extra="forbid")

    media_path: Annotated[
        str | None,
        Field(default=None),
    ]
    enhance: Annotated[
        str | None,
        Field(default=None, max_length=500),
    ]


class PoemSourceCreateInternal(PoemSourceCreate):
    user_id: int
    status: Annotated[
        str,
        Field(default="processing"),
    ]


class PoemSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_path: Annotated[
        str | None,
        Field(default=None),
    ]
    status: Annotated[
        str | None,
        Field(default=None),
    ]


class PoemSourceUpdateInternal(PoemSourceUpdate):
    updated_at: datetime


class PoemSourceDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_deleted: bool
    deleted_at: datetime
