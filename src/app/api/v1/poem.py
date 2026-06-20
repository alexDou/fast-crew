from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_superuser, get_current_user
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import ForbiddenException, NotFoundException
from ...core.utils.cache import cache
from ...crud.crud_poems import crud_poems
from ...models.poet import Poet
from ...schemas.poem import PoemCreate, PoemCreateInternal, PoemRead, PoemUpdate

router = APIRouter(tags=["poems"])


async def _attach_poet_names(db: AsyncSession, poems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    poet_ids = {poem.get("poet_id") for poem in poems if poem.get("poet_id") is not None}
    if not poet_ids:
        return poems

    result = await db.execute(select(Poet.id, Poet.name).where(Poet.id.in_(poet_ids)))
    poet_names_by_id: dict[int, str] = {}
    for poet_id, poet_name in result.all():
        poet_names_by_id[poet_id] = poet_name

    poems_with_poet_names: list[dict[str, Any]] = []
    for poem in poems:
        poet_id = poem.get("poet_id")
        poet_name = poet_names_by_id.get(poet_id) if isinstance(poet_id, int) else None
        poems_with_poet_names.append({**poem, "poet_name": poet_name})

    return poems_with_poet_names


@router.post("/poem", response_model=PoemRead, status_code=201)
async def write_poem(
    request: Request,
    poem: PoemCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> dict[str, Any]:
    if not current_user:
        raise ForbiddenException()

    poem_internal_dict = poem.model_dump()
    poem_internal_dict["created_by_user_id"] = current_user["id"]

    poem_internal = PoemCreateInternal(**poem_internal_dict)
    created_poem = await crud_poems.create(db=db, object=poem_internal, schema_to_select=PoemRead)

    if created_poem is None:
        raise NotFoundException("Failed to create poem")

    return created_poem


@router.get("/poems/{poem_source_id}", response_model=PaginatedListResponse[PoemRead])
@cache(
    key_prefix="{poem_source_id}_poems:page_{page}:items_per_page:{items_per_page}",
    resource_id_name="poem_source_id",
    expiration=60,
)
async def read_poems(
    request: Request,
    poem_source_id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = 1,
    items_per_page: int = 10,
) -> dict:
    if not current_user:
        raise ForbiddenException()

    poems_data = await crud_poems.get_multi(
        db=db,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
        poem_source_id=poem_source_id,
        is_deleted=False,
    )

    response: dict[str, Any] = paginated_response(crud_data=poems_data, page=page, items_per_page=items_per_page)
    response["data"] = await _attach_poet_names(db, response.get("data", []))
    return response


@router.get("/poem/{id}", response_model=PoemRead)
@cache(key_prefix="{id}_poem_cache", resource_id_name="id")
async def read_poem(
    request: Request,
    id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    if not current_user:
        raise ForbiddenException()

    db_poem = await crud_poems.get(
        db=db, id=id, user_id=current_user["id"], is_deleted=False, schema_to_select=PoemRead
    )
    if db_poem is None:
        raise NotFoundException("Poem not found")

    return (await _attach_poet_names(db, [db_poem]))[0]


@router.patch("/poem/{id}")
@cache("{id}_poem_cache", resource_id_name="id", pattern_to_invalidate_extra=["{id}_poems:*"])
async def patch_poem(
    request: Request,
    id: int,
    values: PoemUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> dict[str, str]:
    if not current_user:
        raise ForbiddenException()

    db_poem = await crud_poems.get(db=db, id=id, schema_to_select=PoemRead)
    if db_poem is None:
        raise NotFoundException("Poem not found")

    await crud_poems.update(db=db, object=values, id=id)
    return {"message": "Poem updated"}


@router.delete("/poem/{id}")
@cache("{id}_poem_cache", resource_id_name="id", to_invalidate_extra={"{id}_poems": "{username}"})
async def erase_poem(
    request: Request,
    id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> dict[str, str]:
    if not current_user:
        raise ForbiddenException()

    db_poem = await crud_poems.get(db=db, id=id, schema_to_select=PoemRead)
    if db_poem is None:
        raise NotFoundException("Poem not found")

    await crud_poems.delete(db=db, id=id)

    return {"message": "Poem deleted"}

# hard delete from DB
@router.delete("/db_poem/{id}", dependencies=[Depends(get_current_superuser)])
@cache("{id}_poem_cache", resource_id_name="id", to_invalidate_extra={"{id}_poems": "{id}"})
async def erase_db_poem(
    request: Request,
    id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, str]:
    if not current_user:
        raise ForbiddenException()

    db_poem = await crud_poems.get(db=db, id=id, sschema_to_select=PoemRead)
    if db_poem is None:
        raise NotFoundException("Poem not found")

    await crud_poems.db_delete(db=db, id=id)
    return {"message": "Poem deleted from the database"}
