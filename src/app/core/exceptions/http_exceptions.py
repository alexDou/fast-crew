# ruff: noqa
from fastapi import status
from fastcrud.exceptions.http_exceptions import (
    BadRequestException,
    CustomException,
    ForbiddenException,
    NotFoundException,
    RateLimitException,
    UnauthorizedException,
)


class UnprocessableEntityException(CustomException):
    def __init__(self, detail: str | None = None):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


class DuplicateValueException(CustomException):
    def __init__(self, detail: str | None = None):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)
