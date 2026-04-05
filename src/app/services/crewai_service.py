"""Service for running CrewAI poetry generation in the background."""
import asyncio
import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .storage_service import StorageError, storage_service

logger = logging.getLogger(__name__)


class CrewAIService:
    """Service to run CrewAI poetry generation tasks."""

    INDISTINCT_CONTENT_MESSAGE = "indistinct content"
    MAX_STORED_FAILURE_REASONS = 1000

    def __init__(self):
        # Thread pool for running synchronous CrewAI code
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._failure_reasons: dict[int, tuple[int, str]] = {}
        self._failure_reasons_lock = Lock()

    def get_failure_reason(self, poem_source_id: int, user_id: int) -> str | None:
        with self._failure_reasons_lock:
            stored = self._failure_reasons.get(poem_source_id)
            if not stored:
                return None

            stored_user_id, reason = stored
            if stored_user_id != user_id:
                return None

            return reason

    def _set_failure_reason(self, poem_source_id: int, user_id: int, reason: str) -> None:
        with self._failure_reasons_lock:
            if len(self._failure_reasons) >= self.MAX_STORED_FAILURE_REASONS:
                first_key = next(iter(self._failure_reasons))
                self._failure_reasons.pop(first_key, None)

            self._failure_reasons[poem_source_id] = (user_id, reason)

    @classmethod
    def _extract_failure_reason(cls, exc: Exception) -> str | None:
        normalized = str(exc).strip().lower()
        if normalized == cls.INDISTINCT_CONTENT_MESSAGE:
            return cls.INDISTINCT_CONTENT_MESSAGE
        return None

    async def _update_poem_source_status(
        self,
        db: AsyncSession,
        poem_source_id: int,
        status: str
    ):
        from ..crud.crud_poem_sources import crud_poem_sources
        from ..schemas.poem_source import PoemSourceUpdate

        await crud_poem_sources.update(
            db=db,
            object=PoemSourceUpdate(media_path=None, status=status),
            id=poem_source_id
        )
        await db.commit()

    async def _save_poems(
        self,
        db: AsyncSession,
        user_id: int,
        poem_source_id: int,
        poems: dict[str, str],
    ):
        from datetime import UTC, datetime

        from ..crud.crud_poems import crud_poems
        from ..schemas.poem import PoemCreateInternal

        for poem_text in poems.values():
            if poem_text and poem_text.strip():  # Only save non-empty poems
                # Generate datetime directly to avoid serialization issues
                now = datetime.now(UTC).replace(tzinfo=None)

                poem_data = PoemCreateInternal(
                    user_id=user_id,
                    poem_source_id=poem_source_id,
                    poem=poem_text,
                    created_at=now,
                    updated_at=None
                )

                await crud_poems.create(db=db, object=poem_data)

        await db.commit()

    def _persist_output_artifacts(
        self,
        poem_source_id: int,
        image_analysis: str,
        poems: dict[str, str | None],
    ) -> None:
        """Persist generated markdown artifacts via the configured storage backend."""
        artifacts = {
            "image_analysis.md": image_analysis,
            "poet_modern.md": poems.get("poet_modern") or "",
            "poet_classic.md": poems.get("poet_classic") or "",
            "poet_mystic.md": poems.get("poet_mystic") or "",
        }

        for filename, content in artifacts.items():
            if not content.strip():
                continue

            try:
                output_path = storage_service.store_output_artifact(poem_source_id, filename, content)
                logger.info(f"Stored output artifact for source_id={poem_source_id}: {output_path}")
            except StorageError as exc:
                logger.warning(f"Failed to store output artifact {filename} for source_id={poem_source_id}: {exc}")

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        """Check if an exception is a rate-limit (429) error."""
        # LiteLLM raises litellm.exceptions.RateLimitError,
        # but CrewAI may wrap it — check the class name and message.
        exc_name = type(exc).__name__
        exc_str = str(exc).lower()
        if "ratelimit" in exc_name.lower() or exc_name == "RateLimitError":
            return True
        if "429" in exc_str or "rate limit" in exc_str or "rate_limit" in exc_str:
            return True
        return False

    def _kickoff_with_fallback(self, crew_cls, inputs):
        """Run crew.kickoff(); on rate-limit error, retry with fallback model."""
        try:
            crew_instance = crew_cls()
            return crew_instance.crew().kickoff(inputs=inputs)
        except Exception as e:
            if self._is_rate_limit_error(e):
                fallback = crew_cls.POET_FALLBACK_MODEL
                logger.warning(f"Rate limit hit on default model, retrying with {fallback}: {e}")
                crew_instance = crew_cls(poet_model=fallback)
                return crew_instance.crew().kickoff(inputs=inputs)
            raise

    @staticmethod
    def _resolve_openrouter_api_key() -> str:
        """Resolve OpenRouter API key from settings/env and make it available to imported crew modules."""
        from ..core.config import settings

        configured_key = settings.OPENROUTER_API_KEY.get_secret_value() if settings.OPENROUTER_API_KEY else None
        api_key = configured_key or os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        os.environ["OPENROUTER_API_KEY"] = api_key
        return api_key

    def _run_crew_sync(
        self,
        poem_source_id: int,
        media_path: str,
        user_id: int,
        enhance: str | None,
        db_session_maker
    ) -> dict[str, Any]:
        local_image_path = ""
        should_cleanup_local_image = False

        try:
            local_image_path, should_cleanup_local_image = storage_service.prepare_local_media_file(media_path)
            logger.info(
                f"Starting CrewAI poem generation for source_id={poem_source_id}, "
                f"media={media_path}, local_image={local_image_path}"
            )

            from pathlib import Path

            # CrewAI expects working directory to be the crew root for knowledge sources
            # Detect if running in Docker or locally
            if os.path.exists("/code/crewai_project"):
                base_path = Path("/code")
            else:
                # Find project root by looking for pyproject.toml
                current = Path(__file__).resolve()
                while current.parent != current:
                    if (current / "pyproject.toml").exists():
                        base_path = current
                        break
                    current = current.parent
                else:
                    # Fallback to 3 levels up from this file
                    base_path = Path(__file__).resolve().parent.parent.parent

            crew_root = base_path / "crewai_project" / "crews" / "poets_crew"
            logger.info(f"Base path: {base_path}, Crew root: {crew_root}, Exists: {crew_root.exists()}")
            original_cwd = os.getcwd()
            # Change to crew root for knowledge files
            os.chdir(str(crew_root))
            logger.info(f"Changed directory to {crew_root}")

            # Add the package source directory to sys.path so poets_crew
            # is importable as a proper package (enables relative imports)
            import sys
            pkg_src = str(crew_root / "src")
            if pkg_src not in sys.path:
                sys.path.insert(0, pkg_src)

            openrouter_api_key = self._resolve_openrouter_api_key()

            # Force re-import to pick up any changes
            for mod_name in list(sys.modules):
                if mod_name.startswith("poets_crew"):
                    del sys.modules[mod_name]

            from poets_crew.crew import PoetsCrew
            from poets_crew.tools.image_analyzer_tool import ImageAnalyzerTool
            logger.info(f"Loaded PoetsCrew from package at {pkg_src}")

            # Restore original working directory
            os.chdir(original_cwd)

            # Call ImageAnalyzerTool directly — the agent was not reliably calling it
            tool = ImageAnalyzerTool(
                api_key=openrouter_api_key,
                model="qwen/qwen3-vl-235b-a22b-instruct",
            )
            logger.info(f"Calling ImageAnalyzerTool directly for: {local_image_path}")
            image_analysis = tool._run(image_path=local_image_path)
            logger.info(f"ImageAnalyzerTool result (first 200 chars): {image_analysis[:200]}")

            if image_analysis.strip().lower() == self.INDISTINCT_CONTENT_MESSAGE:
                raise RuntimeError(self.INDISTINCT_CONTENT_MESSAGE)

            inputs = {
                "image_path": local_image_path,
                "image_analysis": image_analysis,
            }
            if enhance:
                inputs["enhance"] = f"\n\nAdditional context from the user: {enhance}"
            else:
                inputs["enhance"] = ""

            logger.info(f"Kicking off PoetsCrew with inputs keys: {list(inputs.keys())}")

            result = self._kickoff_with_fallback(PoetsCrew, inputs)
            logger.info("PoetsCrew completed successfully")

            # Tasks: 0=poet_modern, 1=poet_classic, 2=poet_mystic
            poet_modern = result.tasks_output[0].raw if len(result.tasks_output) > 0 else None
            poet_classic = result.tasks_output[1].raw if len(result.tasks_output) > 1 else None
            poet_mystic = result.tasks_output[2].raw if len(result.tasks_output) > 2 else None

            poems = {
                "poet_modern": poet_modern,
                "poet_classic": poet_classic,
                "poet_mystic": poet_mystic,
            }

            self._persist_output_artifacts(
                poem_source_id=poem_source_id,
                image_analysis=image_analysis,
                poems=poems,
            )

            # Save poems using new async engine in this thread's event loop
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

            from ..core.config import settings

            async def save_results():
                # Create a new engine and session factory for this thread
                database_url = f"{settings.POSTGRES_ASYNC_PREFIX}{settings.POSTGRES_URI}"
                engine = create_async_engine(
                    database_url,
                    echo=False,
                    future=True,
                )
                async_session = async_sessionmaker(
                    engine, class_=AsyncSession, expire_on_commit=False
                )

                async with async_session() as db:
                    try:
                        await self._save_poems(
                            db=db,
                            user_id=user_id,
                            poem_source_id=poem_source_id,
                            poems=poems,
                        )

                        await self._update_poem_source_status(
                            db=db,
                            poem_source_id=poem_source_id,
                            status="success"
                        )
                    except Exception as e:
                        logger.error(f"Error saving poems for source_id={poem_source_id}: {e}")
                        logger.error(traceback.format_exc())
                        await self._update_poem_source_status(
                            db=db,
                            poem_source_id=poem_source_id,
                            status="error"
                        )
                    finally:
                        await engine.dispose()

            # Use new event loop in thread pool
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(save_results())
            finally:
                loop.close()

            return {
                "image_analysis": image_analysis,
                "poems": poems,
                "poet_mystic": poet_mystic
            }

        except Exception as e:
            failure_reason = self._extract_failure_reason(e)
            if failure_reason:
                self._set_failure_reason(poem_source_id, user_id, failure_reason)

            logger.error(f"CRITICAL ERROR in CrewAI service for source_id={poem_source_id}: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")

            # Clean up everything: poems, poem_source record, and uploaded file
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

            from ..core.config import settings

            async def cleanup_on_error():
                database_url = f"{settings.POSTGRES_ASYNC_PREFIX}{settings.POSTGRES_URI}"
                engine = create_async_engine(
                    database_url,
                    echo=False,
                    future=True,
                )
                async_session = async_sessionmaker(
                    engine, class_=AsyncSession, expire_on_commit=False
                )

                async with async_session() as db:
                    try:
                        # Delete any partially saved poems for this source
                        from ..crud.crud_poems import crud_poems
                        await crud_poems.db_delete(
                            db=db,
                            poem_source_id=poem_source_id,
                        )

                        # Hard-delete the poem_source record
                        from ..crud.crud_poem_sources import crud_poem_sources
                        await crud_poem_sources.db_delete(
                            db=db,
                            id=poem_source_id,
                        )

                        await db.commit()
                        logger.info(f"Cleaned up DB records for source_id={poem_source_id}")
                    except Exception as cleanup_err:
                        logger.error(f"DB cleanup failed for source_id={poem_source_id}: {cleanup_err}")
                        await db.rollback()
                    finally:
                        await engine.dispose()

            # Use new event loop in thread pool
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(cleanup_on_error())
            finally:
                loop.close()

            try:
                storage_service.delete_media(media_path)
                logger.info(f"Removed uploaded media: {media_path}")
            except StorageError as file_err:
                logger.error(f"Failed to remove uploaded media {media_path}: {file_err}")

            logger.error(f"Poem generation failed for source_id={poem_source_id}, cleanup complete")
            return {"image_analysis": "", "poems": {}, "poet_mystic": None}
        finally:
            if should_cleanup_local_image and local_image_path and os.path.exists(local_image_path):
                try:
                    os.remove(local_image_path)
                except OSError as exc:
                    logger.warning(f"Failed to clean up temporary local image {local_image_path}: {exc}")

    def start_poem_generation(
        self,
        poem_source_id: int,
        media_path: str,
        user_id: int,
        enhance: str | None,
        db_session_maker
    ) -> None:
        self.executor.submit(
            self._run_crew_sync,
            poem_source_id,
            media_path,
            user_id,
            enhance,
            db_session_maker
        )

crewai_service = CrewAIService()
