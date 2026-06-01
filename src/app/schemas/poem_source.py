import os
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.enums import PoemSourceStatus
from ..core.schemas import PersistentDeletion, TimestampSchema, UUIDSchema
from .poet import PoetCardSchema

__all__ = [
    "PoemSource",
    "PoemSourceAnswerSubmission",
    "PoemSourceAnswerSubmissionAccepted",
    "PoemSourceCreate",
    "PoemSourceCreateInternal",
    "PoemSourceDelete",
    "PoemSourcePatch",
    "PoemSourceQuestion",
    "PoemSourceRead",
    "PoemSourceStatus",
    "PoemSourceStatusResponse",
    "PoemSourceUpdate",
    "PoemSourceUpdateInternal",
    "PoemSourceWorkflowRead",
]

base_media_path = os.path.join(os.getcwd(), "media/")


class PoemSourceBase(BaseModel):
    pass


class PoemSourceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=20)]
    text: Annotated[str, Field(min_length=1, max_length=500)]


class PoemSourceAnswerSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str]

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, values: dict[str, str]) -> dict[str, str]:
        if not values:
            raise ValueError("At least one answer is required")

        normalized_answers: dict[str, str] = {}
        for question_id, answer in values.items():
            normalized_question_id = question_id.strip()
            normalized_answer = answer.strip()
            if not normalized_question_id or not normalized_answer:
                raise ValueError("Answers must include non-empty question ids and values")
            normalized_answers[normalized_question_id] = normalized_answer

        return normalized_answers


class PoemSourceAnswerSubmissionAccepted(BaseModel):
    message: str
    status: str
    poem_source_id: int


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
        Field(default=PoemSourceStatus.PROCESSING.value),
    ]
    image_analysis: Annotated[
        str | None,
        Field(default=None),
    ]
    follow_up_questions: list[PoemSourceQuestion] | None = None
    follow_up_answers: dict[str, str] | None = None
    poet_candidates: list[PoetCardSchema] | None = None
    error_message: str | None = None


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
        Field(default=PoemSourceStatus.PROCESSING.value),
    ]
    user_id: int
    created_at: datetime
    poet_candidates: list[PoetCardSchema] | None = None


class PoemSourceWorkflowRead(PoemSourceRead):
    image_analysis: str | None = None
    follow_up_questions: list[PoemSourceQuestion] | None = None
    follow_up_answers: dict[str, str] | None = None
    poet_candidates: list[PoetCardSchema] | None = None
    error_message: str | None = None
    updated_at: datetime | None = None


class PoemSourceStatusResponse(BaseModel):
    ready: bool
    status: str
    poem_source_id: int
    message: str | None = None
    questions: list[PoemSourceQuestion] = Field(default_factory=list)
    poet_candidates: list[PoetCardSchema] = Field(default_factory=list)


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
        Field(default=PoemSourceStatus.PROCESSING.value),
    ]


class PoemSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_path: str | None = None
    enhance: str | None = None
    status: str | None = None
    image_analysis: str | None = None
    follow_up_questions: list[PoemSourceQuestion] | None = None
    follow_up_answers: dict[str, str] | None = None
    poet_candidates: list[PoetCardSchema] | None = None
    error_message: str | None = None


class PoemSourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_path: str | None = None
    enhance: str | None = None


class PoemSourceUpdateInternal(PoemSourceUpdate):
    updated_at: datetime


class PoemSourceDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_deleted: bool
    deleted_at: datetime
