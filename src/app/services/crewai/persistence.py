"""Async persistence helpers for CrewAI worker threads.

Each CrewAI stage runs in a dedicated thread. The main FastAPI event
loop's ``AsyncSession`` cannot be shared across threads, so stage code
spins up its own engine + session via :func:`with_thread_db` and
executes an async callback inside it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .prompts import VARIANT_LABELS

T = TypeVar("T")


def run_async(awaitable: Awaitable[T]) -> T:
    """Run ``awaitable`` on a fresh event loop and return its result.

    Used from synchronous CrewAI worker threads that do not have a
    running event loop of their own. The loop is always closed, even
    when the awaitable raises.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(awaitable)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


async def with_thread_db(callback: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run ``callback`` with a freshly-scoped AsyncSession + engine.

    The engine is disposed on exit so worker threads never leak
    connections back to the pool belonging to the main event loop.
    """
    from ...core.config import settings

    engine = create_async_engine(
        settings.POSTGRES_ASYNC_DATABASE_URL,
        echo=False,
        future=True,
    )
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            return await callback(db)
    finally:
        await engine.dispose()


async def update_poem_source(
    db: AsyncSession,
    poem_source_id: int,
    *,
    commit: bool = True,
    **values: Any,
) -> None:
    """Patch a ``poem_source`` row with only the provided fields.

    ``PoemSourceUpdate`` is constructed from ``**values`` so unset fields
    are *not* serialized by FastCRUD, keeping ``media_path``,
    ``image_analysis``, ``follow_up_questions`` and ``follow_up_answers``
    intact across partial status updates.
    """
    from ...crud.crud_poem_sources import crud_poem_sources
    from ...schemas.poem_source import PoemSourceUpdate

    await crud_poem_sources.update(
        db=db,
        object=PoemSourceUpdate(**values),
        id=poem_source_id,
    )
    if commit:
        await db.commit()


async def update_poem_source_status(
    db: AsyncSession,
    poem_source_id: int,
    status: str,
) -> None:
    """Convenience wrapper: patch only the ``status`` column and commit."""
    await update_poem_source(db, poem_source_id, status=status)


async def save_poems(
    db: AsyncSession,
    user_id: int,
    poem_source_id: int,
    poems: dict[str, str],
    *,
    commit: bool = True,
) -> None:
    """Persist one row per non-empty variant, tagged with its author label."""
    from ...crud.crud_poems import crud_poems
    from ...schemas.poem import PoemCreateInternal

    for variant_key, poem_text in poems.items():
        if not (poem_text and poem_text.strip()):
            continue

        # Generate datetime directly to avoid serialization issues in the
        # PoemCreateInternal schema (datetime strings vs datetime objects).
        now = datetime.now(UTC).replace(tzinfo=None)

        poem_data = PoemCreateInternal(
            user_id=user_id,
            poem_source_id=poem_source_id,
            poem=poem_text,
            variant_key=variant_key,
            author_label=VARIANT_LABELS.get(variant_key),
            created_at=now,
            updated_at=None,
        )

        await crud_poems.create(db=db, object=poem_data)

    if commit:
        await db.commit()
