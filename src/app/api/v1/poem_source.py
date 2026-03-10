from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_superuser, get_current_user
from ...core.db.database import async_get_db, local_session
from ...core.exceptions.http_exceptions import ForbiddenException, NotFoundException
from ...core.utils.cache import cache
from ...crud.crud_poem_sources import crud_poem_sources
from ...schemas.poem_source import PoemSourceCreateInternal, PoemSourceRead, PoemSourceUpdate
from ...services.crewai_service import crewai_service
from ...services.storage_service import StorageError, storage_service

router = APIRouter(tags=["poems_source"])


@router.post("/poem-source", response_model=PoemSourceRead, status_code=201)
async def write_poem_source(
    request: Request,
    file: UploadFile = File(...),
    enhance: str | None = None,
    current_user: Annotated[dict, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(async_get_db)] = None,
) -> dict[str, Any]:
    """Create a poem source by uploading an image file.

    Args:
        username: The username of the user creating the poem source
        file: Image file to upload
        current_user: The authenticated user
        db: Database session

    Returns:
        The created poem source record with the file path
    """
    if not current_user:
        raise ForbiddenException()

    # Validate file type (images only)
    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    filename = file.filename or ""
    file_extension = Path(filename).suffix.lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_extension} not allowed. Allowed types: {', '.join(allowed_extensions)}"
        )

    object_key = storage_service.build_media_object_key(current_user["username"], file_extension)

    try:
        media_path = await storage_service.upload_upload_file(file=file, object_key=object_key)
    except StorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await file.close()

    # Create the poem source record with processing status
    poem_source_internal_dict = {
        "media_path": media_path,
        "user_id": current_user["id"],
        "enhance": enhance,
        "status": "processing"
    }

    poem_source_internal = PoemSourceCreateInternal(**poem_source_internal_dict)
    created_poem_source = await crud_poem_sources.create(
        db=db,
        object=poem_source_internal,
        schema_to_select=PoemSourceRead
    )

    if created_poem_source is None:
        raise NotFoundException("Failed to create poem source")

    # Start CrewAI poem generation in the background
    crewai_service.start_poem_generation(
        poem_source_id=created_poem_source["id"],
        media_path=media_path,
        user_id=current_user["id"],
        enhance=enhance,
        db_session_maker=local_session
    )

    return storage_service.attach_media_url(created_poem_source)


@router.get("/poem-sources", response_model=PaginatedListResponse[PoemSourceRead])
async def read_poem_sources(
    request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = 1,
    items_per_page: int = 10,
) -> dict:
    poem_sources_data = await crud_poem_sources.get_multi(
        db=db,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
        user_id=current_user["id"],
        is_deleted=False,
    )

    response: dict[str, Any] = paginated_response(crud_data=poem_sources_data, page=page, items_per_page=items_per_page)
    response["data"] = [storage_service.attach_media_url(item) for item in response.get("data", [])]
    return response


@router.get("/poem-source/{id}/ready")
async def check_poem_source_ready(
    request: Request,
    id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    """Check if poem generation is complete for a poem source.

    Args:
        username: The username of the user
        id: The poem source ID
        db: Database session

    Returns:
        Dictionary with status information:
        - ready: bool (True if success or error, False if still processing)
        - status: str (processing, success, or error)
        - poem_source_id: int
    """
    db_poem_source = await crud_poem_sources.get(
        db=db,
        id=id,
        user_id=current_user["id"],
        is_deleted=False,
        schema_to_select=PoemSourceRead
    )

    if db_poem_source is None:
        raise NotFoundException("Poem source not found")

    status = db_poem_source.get("status", "processing")
    is_ready = status in ["success", "error"]

    return {
        "ready": is_ready,
        "status": status,
        "poem_source_id": id
    }


@router.get("/poem_source/{id}", response_model=PoemSourceRead)
@cache(key_prefix="{id}_poem_source_cache", resource_id_name="id")
async def read_poem_source(
    request: Request,
    id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    db_poem_source = await crud_poem_sources.get(
        db=db, id=id, user_id=current_user["id"], is_deleted=False, schema_to_select=PoemSourceRead
    )

    if db_poem_source is None:
        raise NotFoundException("Poem source not found")

    return storage_service.attach_media_url(db_poem_source)


@router.patch("/poem_source/{id}")
@cache("{id}_poem_source_cache", resource_id_name="id", pattern_to_invalidate_extra=["{id}_poem_sources:*"])
async def patch_poem_source(
    request: Request,
    id: int,
    values: PoemSourceUpdate,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, str]:
    if not current_user:
        raise ForbiddenException()

    db_poem_source = await crud_poem_sources.get(db=db, id=id, is_deleted=False, schema_to_select=PoemSourceRead)

    if db_poem_source is None:
        raise NotFoundException("Poem source not found")

    await crud_poem_sources.update(db=db, object=values, id=id)
    return {"message": "Poem source updated"}


@router.delete("/poem-source/{id}")
@cache("{id}_poem_source_cache", resource_id_name="id", to_invalidate_extra={"{id}_poem_sources": "{id}"})
async def erase_poem_source(
    request: Request,
    id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> dict[str, str]:
    if not current_user:
        raise ForbiddenException()

    db_poem_source = await crud_poem_sources.get(db=db, id=id, is_deleted=False, schema_to_select=PoemSourceRead)
    if db_poem_source is None:
        raise NotFoundException("Poem source not found")

    await crud_poem_sources.delete(db=db, id=id)

    return {"message": "Poem deleted"}

# hard delete from DB
@router.delete("/db_poem_source/{id}", dependencies=[Depends(get_current_superuser)])
@cache("{id}_poem_source_cache", resource_id_name="id", to_invalidate_extra={"{id}_poems": "{id}"})
async def erase_db_poem_source(
    request: Request,
    id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, str]:
    if not current_user:
        raise ForbiddenException()

    db_poem_source = await crud_poem_sources.get(db=db, id=id, is_deleted=False, schema_to_select=PoemSourceRead)

    if db_poem_source is None:
        raise NotFoundException("Poem source not found")

    await crud_poem_sources.db_delete(db=db, id=id)
    return {"message": "Poem source deleted from the database"}
