from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_superuser, get_current_user
from ...core.config import settings
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import DuplicateValueException, ForbiddenException, NotFoundException
from ...core.security import blacklist_token, create_email_verification_token, get_password_hash, oauth2_scheme
from ...crud.crud_users import crud_users
from ...schemas.user import ResendVerificationRequest, UserCreate, UserCreateInternal, UserRead, UserUpdate
from ...services.email_service import VerificationEmailPayload, email_service


def _request_origin(request: Request) -> str:
    if settings.EMAIL_VERIFICATION_BASE_URL:
        return settings.EMAIL_VERIFICATION_BASE_URL.rstrip("/")
    if settings.CORS_ORIGINS and settings.CORS_ORIGINS[0] != "*":
        return settings.CORS_ORIGINS[0]
    return str(request.base_url).rstrip("/")


async def _send_verification_email(request: Request, to_email: str, to_name: str | None, token: str) -> None:
    verification_link = email_service.build_verification_link(_request_origin(request), token)
    await email_service.send_verification_email(
        VerificationEmailPayload(
            to_email=to_email,
            to_name=to_name,
            verification_link=verification_link,
        )
    )

router = APIRouter(tags=["users"])


@router.post("/user", response_model=UserRead, status_code=201)
async def write_user(
    request: Request, user: UserCreate, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, Any]:
    existing_user = await crud_users.get(db=db, email=user.email, is_deleted=False)
    if existing_user:
        if existing_user.get("is_email_verified", False):
            raise DuplicateValueException("Email is already registered")

        created_at: datetime | None = existing_user.get("created_at")
        if created_at is None:
            raise DuplicateValueException("Email is not yet verified, please check your email")

        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        expires_after = timedelta(days=settings.EMAIL_VERIFICATION_EXPIRE_DAYS)
        if (datetime.now(UTC) - created_at) < expires_after:
            raise DuplicateValueException("Email is not yet verified, please check your email")

        await crud_users.db_delete(db=db, id=existing_user["id"])

    username_row = await crud_users.exists(db=db, username=user.username)
    if username_row:
        raise DuplicateValueException("Username not available")

    user_internal_dict = user.model_dump()
    user_internal_dict["hashed_password"] = get_password_hash(password=user_internal_dict["password"])
    del user_internal_dict["password"]

    user_internal = UserCreateInternal(**user_internal_dict)
    created_user = await crud_users.create(db=db, object=user_internal, schema_to_select=UserRead)

    if created_user is None:
        raise NotFoundException("Failed to create user")

    try:
        verification_token = await create_email_verification_token(data={"sub": user.email})
        await _send_verification_email(request=request, to_email=user.email, to_name=user.name, token=verification_token)
    except Exception:
        import structlog
        structlog.get_logger(__name__).error("Failed to send verification email during signup", email=user.email)

    return created_user


@router.get("/users", response_model=PaginatedListResponse[UserRead])
async def read_users(
    request: Request, db: Annotated[AsyncSession, Depends(async_get_db)], page: int = 1, items_per_page: int = 10
) -> dict:
    users_data = await crud_users.get_multi(
        db=db,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
        is_deleted=False,
    )

    response: dict[str, Any] = paginated_response(crud_data=users_data, page=page, items_per_page=items_per_page)
    return response


@router.get("/user/me", response_model=UserRead)
async def read_users_me(request: Request, current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
    return current_user


@router.get("/user/{username}", response_model=UserRead)
async def read_user(
    request: Request, username: str, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, Any]:
    db_user = await crud_users.get(db=db, username=username, is_deleted=False, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")

    return db_user


@router.patch("/user/{username}")
async def patch_user(
    request: Request,
    values: UserUpdate,
    username: str,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> dict[str, str]:
    db_user = await crud_users.get(db=db, username=username)
    if db_user is None:
        raise NotFoundException("User not found")

    db_username = db_user["username"]
    db_email = db_user["email"]

    if db_username != current_user["username"]:
        raise ForbiddenException()

    if values.email is not None and values.email != db_email:
        if await crud_users.exists(db=db, email=values.email):
            raise DuplicateValueException("Email is already registered")

    if values.username is not None and values.username != db_username:
        if await crud_users.exists(db=db, username=values.username):
            raise DuplicateValueException("Username not available")

    await crud_users.update(db=db, object=values, username=username)
    return {"message": "User updated"}


@router.delete("/user/{username}")
async def erase_user(
    request: Request,
    username: str,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
    token: str = Depends(oauth2_scheme),
) -> dict[str, str]:
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if not db_user:
        raise NotFoundException("User not found")

    if username != current_user["username"]:
        raise ForbiddenException()

    await crud_users.delete(db=db, username=username)
    await blacklist_token(token=token, db=db)
    return {"message": "User deleted"}

# hard delete from DB
@router.delete("/db_user/{username}", dependencies=[Depends(get_current_superuser)])
async def erase_db_user(
    request: Request,
    username: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    token: str = Depends(oauth2_scheme),
) -> dict[str, str]:
    db_user = await crud_users.exists(db=db, username=username)
    if not db_user:
        raise NotFoundException("User not found")

    await crud_users.db_delete(db=db, username=username)
    await blacklist_token(token=token, db=db)
    return {"message": "User deleted from the database"}


@router.get("/verify-email")
async def verify_email(
    request: Request,
    token: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> RedirectResponse:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY.get_secret_value(), algorithms=[settings.ALGORITHM])
        email: str | None = payload.get("sub")
        purpose: str | None = payload.get("purpose")
        if email is None or purpose != "email_verification":
            raise NotFoundException("Invalid verification link")
    except JWTError:
        raise NotFoundException("Invalid or expired verification link")

    db_user = await crud_users.get(db=db, email=email, is_deleted=False)
    if db_user is None:
        raise NotFoundException("User not found")

    login_url = f"{_request_origin(request)}/signin"

    if db_user.get("is_email_verified", False):
        return RedirectResponse(url=login_url, status_code=303)

    # Direct SQL update for is_email_verified since it's not in UserUpdate schema
    from sqlalchemy import update as sql_update

    from ...models.user import User as UserModel
    stmt = sql_update(UserModel).where(UserModel.email == email).values(is_email_verified=True)
    await db.execute(stmt)
    await db.commit()

    return RedirectResponse(url=login_url, status_code=303)


@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> dict[str, str]:
    identifier = payload.resolved_identifier

    if "@" in identifier:
        db_user = await crud_users.get(db=db, email=identifier, is_deleted=False)
    else:
        db_user = await crud_users.get(db=db, username=identifier, is_deleted=False)

    if db_user is None:
        return {"message": "If this email is registered, a verification link has been sent."}

    if db_user.get("is_email_verified", False):
        return {"message": "Email is already verified."}

    verification_token = await create_email_verification_token(data={"sub": db_user["email"]})
    await _send_verification_email(
        request=request,
        to_email=db_user["email"],
        to_name=db_user.get("name"),
        token=verification_token,
    )

    return {"message": "If this email is registered, a verification link has been sent."}
