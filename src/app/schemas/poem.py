import os
import re

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.schemas import PersistentDeletion, TimestampSchema


base_media_path = os.path.join(os.getcwd(), "media/")
def sanitize(poem: str) -> str:
    return re.sub("<[^<]+?>", "", poem)


class PoemBase(TimestampSchema, BaseModel):
    poem_source_id: int
    poem: Annotated[str, Field(min_length=2, max_length=6320)]

    @field_validator("poem")
    def validate_and_sanitize_path(cls, v: str) -> str:
        return sanitize(v)


class Poem(PoemBase, PersistentDeletion):
  user_id: int
  critic_choice: bool = False


class PoemRead(BaseModel):
    id: int

    user_id: int
    poem_source_id: int

    poem: Annotated[str, Field(min_length=40, max_length=6320)]
    critic_choice: bool = False

    created_at: datetime
    updated_at: datetime | None


class PoemCreate(PoemBase):
    model_config = ConfigDict(extra="forbid")


class PoemCreateInternal(BaseModel):
    """Internal schema for creating poems without timestamp serialization."""
    model_config = ConfigDict(extra="forbid")
    
    user_id: int
    poem_source_id: int
    poem: Annotated[str, Field(min_length=2, max_length=6320)]
    critic_choice: bool = False
    created_at: datetime
    updated_at: datetime | None = None
    
    @field_validator("poem")
    def validate_and_sanitize_path(cls, v: str) -> str:
        return sanitize(v)


class PoemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poem: Optional[str]
    critic_choice: Optional[bool]


class PoemUpdateInternal(PoemUpdate):
    updated_at: datetime


class PoemDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_deleted: bool
    deleted_at: datetime

