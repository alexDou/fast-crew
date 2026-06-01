"""Staged CrewAI orchestration service.

Two public entrypoints, :meth:`CrewAIService.start_stage_1_analysis` and
:meth:`CrewAIService.start_stage_2_generation`, submit synchronous work
to a shared ``ThreadPoolExecutor`` (max 3 workers). Each stage owns its
own DB session via :mod:`.persistence` so it can safely write back
results from a non-event-loop thread.
"""

from __future__ import annotations

import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.enums import PoemSourceStatus
from ..storage_service import storage_service
from . import persistence
from .artifacts import persist_output_artifacts
from .crew_loader import load_poets_crew_modules, resolve_openrouter_api_key
from .errors import INDISTINCT_CONTENT_MESSAGE, is_rate_limit_error, normalize_error_message
from .prompts import (
    generate_follow_up_questions,
    generate_poet_candidate_ids,
    generate_stage_2_poem,
)

logger = logging.getLogger(__name__)

IMAGE_ANALYZER_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"
ERROR_ANALYZING_IMAGE_PREFIX = "error analyzing image:"
MAX_WORKERS = 3


class CrewAIService:
    """Thread-pool backed orchestrator for the staged poem workflow."""

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    # ------------------------------------------------------------------
    # Public entrypoints
    # ------------------------------------------------------------------

    def start_stage_1_analysis(
        self,
        poem_source_id: int,
        media_path: str,
        user_id: int,
        enhance: str | None,
    ) -> None:
        """Submit stage-1 (image analysis + question generation) work."""
        self.executor.submit(
            self._run_stage_1_sync,
            poem_source_id,
            media_path,
            user_id,
            enhance,
        )

    def start_stage_2_generation(self, poem_source_id: int, poet_id: int | None = None) -> None:
        """Submit stage-2 (poem generation from persisted Q/A + analysis)."""
        self.executor.submit(self._run_stage_2_sync, poem_source_id, poet_id)

    # ------------------------------------------------------------------
    # Compatibility shims retained for tests + incremental migration
    # ------------------------------------------------------------------

    async def _update_poem_source(
        self,
        db: AsyncSession,
        poem_source_id: int,
        *,
        commit: bool = True,
        **values: Any,
    ) -> None:
        await persistence.update_poem_source(db, poem_source_id, commit=commit, **values)

    async def _update_poem_source_status(
        self,
        db: AsyncSession,
        poem_source_id: int,
        status: str,
    ) -> None:
        await persistence.update_poem_source_status(db, poem_source_id, status)

    async def _save_poem(
        self,
        db: AsyncSession,
        user_id: int,
        poem_source_id: int,
        poem: str,
        poet_id: int | None = None,
        *,
        commit: bool = True,
    ) -> None:
        await persistence.save_poem(
            db,
            user_id=user_id,
            poem_source_id=poem_source_id,
            poet_id=poet_id,
            poem=poem,
            commit=commit,
        )

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _kickoff_with_fallback(self, crew_cls: Any, inputs: dict[str, Any]) -> Any:
        """Run ``crew.kickoff(inputs=inputs)``; retry on rate-limit errors.

        When the default poet model hits a 429 we re-instantiate the crew
        with ``POET_FALLBACK_MODEL`` so transient upstream pressure does
        not surface to the user as a workflow failure.
        """
        try:
            crew_instance = crew_cls()
            return crew_instance.crew().kickoff(inputs=inputs)
        except Exception as exc:
            if is_rate_limit_error(exc):
                fallback = crew_cls.POET_FALLBACK_MODEL
                logger.warning("Rate limit hit on default model, retrying with %s: %s", fallback, exc)
                crew_instance = crew_cls(poet_model=fallback)
                return crew_instance.crew().kickoff(inputs=inputs)
            raise

    def _run_stage_1_sync(
        self,
        poem_source_id: int,
        media_path: str,
        user_id: int,
        enhance: str | None,
    ) -> dict[str, Any]:
        """Analyze the image, generate questions, and persist stage-1 output."""
        local_image_path = ""
        should_cleanup_local_image = False

        try:
            _, ImageAnalyzerTool, openrouter_api_key = load_poets_crew_modules()
            local_image_path, should_cleanup_local_image = storage_service.prepare_local_media_file(
                media_path
            )

            tool = ImageAnalyzerTool(api_key=openrouter_api_key, model=IMAGE_ANALYZER_MODEL)
            image_analysis = tool._run(image_path=local_image_path).strip()
            logger.info("Stage 1 image analysis completed for source_id=%s", poem_source_id)

            self._raise_if_indistinct(image_analysis)

            active_poets = self._load_active_poets()
            with ThreadPoolExecutor(max_workers=2) as stage_1_executor:
                questions_future = stage_1_executor.submit(
                    generate_follow_up_questions,
                    image_analysis,
                    enhance,
                    openrouter_api_key,
                )
                poet_ids_future = stage_1_executor.submit(
                    generate_poet_candidate_ids,
                    image_analysis,
                    active_poets,
                    openrouter_api_key,
                    poem_source_id,
                )

                questions = questions_future.result()
                try:
                    poet_ids = poet_ids_future.result()
                except Exception as exc:
                    logger.warning("Poet picker failed for source_id=%s: %s", poem_source_id, exc)
                    poet_ids = []

            poet_candidates = self._load_poet_cards(poet_ids)
            persist_output_artifacts(
                poem_source_id=poem_source_id, image_analysis=image_analysis
            )

            async def persist_stage_1(db: AsyncSession) -> None:
                await persistence.update_poem_source(
                    db,
                    poem_source_id,
                    status=PoemSourceStatus.STAGE_1.value,
                    image_analysis=image_analysis,
                    follow_up_questions=questions,
                    poet_candidates=poet_candidates,
                    error_message=None,
                )

            persistence.run_async(persistence.with_thread_db(persist_stage_1))
            return {"image_analysis": image_analysis, "questions": questions, "poet_candidates": poet_candidates}
        except Exception as exc:
            self._persist_stage_failure(
                poem_source_id=poem_source_id, stage_label="Stage 1", exc=exc
            )
            return {"image_analysis": "", "questions": [], "poet_candidates": []}
        finally:
            self._cleanup_local_image(local_image_path, should_cleanup_local_image)

    def _run_stage_2_sync(self, poem_source_id: int, poet_id: int | None = None) -> dict[str, Any]:
        """Generate poems from persisted ``image_analysis`` + ``follow_up_answers``."""
        local_image_path = ""
        should_cleanup_local_image = False

        try:
            openrouter_api_key = resolve_openrouter_api_key()

            poem_source = self._load_poem_source(poem_source_id)
            if poem_source is None:
                raise RuntimeError("Poem source not found")

            user_id = poem_source.get("user_id")
            image_analysis = poem_source.get("image_analysis")
            questions = poem_source.get("follow_up_questions") or []
            answers = poem_source.get("follow_up_answers") or {}

            if not user_id or not image_analysis:
                raise RuntimeError("Poem source is missing staged workflow data")

            poet_name = self._load_poet_name(poet_id) if poet_id is not None else None
            if poet_id is not None and poet_name is None:
                raise RuntimeError("Selected poet not found")
            poem_text = generate_stage_2_poem(
                openrouter_api_key,
                image_analysis,
                questions,
                answers,
                poet_name,
            )
            persist_output_artifacts(
                poem_source_id=poem_source_id, image_analysis=image_analysis, poem=poem_text
            )

            async def persist_stage_2(db: AsyncSession) -> None:
                try:
                    await persistence.save_poem(
                        db,
                        user_id=user_id,
                        poem_source_id=poem_source_id,
                        poet_id=poet_id,
                        poem=poem_text,
                        commit=False,
                    )
                    await persistence.update_poem_source(
                        db,
                        poem_source_id,
                        status=PoemSourceStatus.COMPLETE.value,
                        error_message=None,
                        commit=False,
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

            persistence.run_async(persistence.with_thread_db(persist_stage_2))
            return {"image_analysis": image_analysis, "poem": poem_text}
        except Exception as exc:
            self._persist_stage_failure(
                poem_source_id=poem_source_id, stage_label="Stage 2", exc=exc
            )
            return {"image_analysis": "", "poem": ""}
        finally:
            self._cleanup_local_image(local_image_path, should_cleanup_local_image)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _raise_if_indistinct(image_analysis: str) -> None:
        """Translate the vision-model sentinel values into a stage failure.

        The analyzer signals ambiguous inputs by returning the literal
        ``"indistinct content"`` or an ``"Error analyzing image: ..."``
        line. Either surface as a ``RuntimeError`` so the outer handler
        records a durable ``error_message`` on the workflow row.
        """
        normalized = image_analysis.lower()
        if normalized == INDISTINCT_CONTENT_MESSAGE:
            raise RuntimeError(INDISTINCT_CONTENT_MESSAGE)
        if normalized.startswith(ERROR_ANALYZING_IMAGE_PREFIX):
            raise RuntimeError(image_analysis)

    @staticmethod
    def _load_active_poets() -> list[dict[str, Any]]:
        """Load active poets in the minimal ``{id, name}`` picker shape."""

        async def load(db: AsyncSession) -> list[dict[str, Any]]:
            from sqlalchemy import select

            from ...models.poet import Poet
            from ...schemas.poet import PoetSelectorItemSchema

            result = await db.execute(select(Poet).where(Poet.is_active.is_(True)).order_by(Poet.name))
            return [
                PoetSelectorItemSchema.model_validate(poet).model_dump()
                for poet in result.scalars().all()
            ]

        return persistence.run_async(persistence.with_thread_db(load))

    @staticmethod
    def _load_poet_cards(poet_ids: list[int]) -> list[dict[str, Any]]:
        """Load full poet card payloads for picked IDs, preserving picker order."""
        if not poet_ids:
            return []

        async def load(db: AsyncSession) -> list[dict[str, Any]]:
            from sqlalchemy import select

            from ...models.poet import Poet
            from ...schemas.poet import PoetCardSchema

            result = await db.execute(select(Poet).where(Poet.id.in_(poet_ids), Poet.is_active.is_(True)))
            poets_by_id = {poet.id: poet for poet in result.scalars().all()}
            return [
                PoetCardSchema.model_validate(poets_by_id[poet_id]).model_dump()
                for poet_id in poet_ids
                if poet_id in poets_by_id
            ]

        return persistence.run_async(persistence.with_thread_db(load))

    @staticmethod
    def _load_poet_name(poet_id: int) -> str | None:
        """Load the active poet name used by the Stage 2 prompt."""

        async def load(db: AsyncSession) -> str | None:
            from sqlalchemy import select

            from ...models.poet import Poet

            result = await db.execute(select(Poet.name).where(Poet.id == poet_id, Poet.is_active.is_(True)))
            return result.scalar_one_or_none()

        return persistence.run_async(persistence.with_thread_db(load))

    @staticmethod
    def _load_poem_source(poem_source_id: int) -> dict[str, Any] | None:
        async def load(db: AsyncSession) -> dict[str, Any] | None:
            from ...crud.crud_poem_sources import crud_poem_sources
            from ...schemas.poem_source import PoemSourceWorkflowRead

            return await crud_poem_sources.get(
                db=db,
                id=poem_source_id,
                is_deleted=False,
                schema_to_select=PoemSourceWorkflowRead,
            )

        return persistence.run_async(persistence.with_thread_db(load))

    @staticmethod
    def _persist_stage_failure(*, poem_source_id: int, stage_label: str, exc: Exception) -> None:
        """Log the failure and mark the workflow row with a durable error message."""
        logger.error("%s failed for source_id=%s: %s", stage_label, poem_source_id, exc)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        error_message = normalize_error_message(exc)

        async def persist_error(db: AsyncSession) -> None:
            await persistence.update_poem_source(
                db,
                poem_source_id,
                status=PoemSourceStatus.ERROR.value,
                error_message=error_message,
            )

        persistence.run_async(persistence.with_thread_db(persist_error))

    @staticmethod
    def _cleanup_local_image(local_image_path: str, should_cleanup: bool) -> None:
        if not (should_cleanup and local_image_path and os.path.exists(local_image_path)):
            return
        try:
            os.remove(local_image_path)
        except OSError as cleanup_error:
            logger.warning(
                "Failed to clean up temporary local image %s: %s",
                local_image_path,
                cleanup_error,
            )


crewai_service = CrewAIService()
