"""Service for running CrewAI poetry generation in the background."""

import asyncio
import json
import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from .storage_service import StorageError, storage_service

logger = logging.getLogger(__name__)


class CrewAIService:
    """Service to run CrewAI poetry generation tasks."""

    INDISTINCT_CONTENT_MESSAGE = "indistinct content"
    QUESTION_MODEL = "openrouter/deepseek/deepseek-v3.2"
    VARIANT_LABELS = {
        "poet_modern": "Modern Poet",
        "poet_classic": "Classic Poet",
        "poet_mystic": "Mystic Poet",
    }

    def __init__(self):
        # Thread pool for running synchronous CrewAI code
        self.executor = ThreadPoolExecutor(max_workers=3)

    async def _update_poem_source(
        self,
        db: AsyncSession,
        poem_source_id: int,
        *,
        commit: bool = True,
        **values: Any,
    ) -> None:
        from ..crud.crud_poem_sources import crud_poem_sources
        from ..schemas.poem_source import PoemSourceUpdate

        await crud_poem_sources.update(
            db=db,
            object=PoemSourceUpdate(**values),
            id=poem_source_id,
        )
        if commit:
            await db.commit()

    async def _update_poem_source_status(
        self,
        db: AsyncSession,
        poem_source_id: int,
        status: str,
    ) -> None:
        await self._update_poem_source(db, poem_source_id, status=status)

    async def _save_poems(
        self,
        db: AsyncSession,
        user_id: int,
        poem_source_id: int,
        poems: dict[str, str],
        *,
        commit: bool = True,
    ) -> None:
        from datetime import UTC, datetime

        from ..crud.crud_poems import crud_poems
        from ..schemas.poem import PoemCreateInternal

        for variant_key, poem_text in poems.items():
            if poem_text and poem_text.strip():  # Only save non-empty poems
                # Generate datetime directly to avoid serialization issues
                now = datetime.now(UTC).replace(tzinfo=None)

                poem_data = PoemCreateInternal(
                    user_id=user_id,
                    poem_source_id=poem_source_id,
                    poem=poem_text,
                    variant_key=variant_key,
                    author_label=self.VARIANT_LABELS.get(variant_key),
                    created_at=now,
                    updated_at=None,
                )

                await crud_poems.create(db=db, object=poem_data)

        if commit:
            await db.commit()

    def _persist_output_artifacts(
        self,
        poem_source_id: int,
        image_analysis: str | None = None,
        poems: dict[str, str | None] | None = None,
    ) -> None:
        """Persist generated markdown artifacts via the configured storage backend."""
        artifacts: dict[str, str] = {}
        if image_analysis:
            artifacts["image_analysis.md"] = image_analysis
        if poems:
            artifacts.update({
                "poet_modern.md": poems.get("poet_modern") or "",
                "poet_classic.md": poems.get("poet_classic") or "",
                "poet_mystic.md": poems.get("poet_mystic") or "",
            })

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
        """Resolve OpenRouter API key from settings and expose it to imported crew modules."""
        from ..core.config import settings

        if not settings.OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        api_key = settings.OPENROUTER_API_KEY.get_secret_value()
        os.environ["OPENROUTER_API_KEY"] = api_key
        return api_key

    @staticmethod
    def _extract_text_content(content: Any) -> str:
        if isinstance(content, list):
            return "".join(str(part) for part in content).strip()
        return str(content or "").strip()

    @staticmethod
    def _normalize_error_message(exc: Exception) -> str:
        message = str(exc).strip()
        if not message:
            return "Poem generation failed"
        return message.splitlines()[0][:1000]

    @staticmethod
    def _resolve_crewai_root() -> tuple[str, str]:
        from pathlib import Path

        if os.path.exists("/code/crewai_project"):
            base_path = Path("/code")
        else:
            current = Path(__file__).resolve()
            while current.parent != current:
                if (current / "pyproject.toml").exists():
                    base_path = current
                    break
                current = current.parent
            else:
                base_path = Path(__file__).resolve().parent.parent.parent

        crew_root = base_path / "crewai_project" / "crews" / "poets_crew"
        return str(base_path), str(crew_root)

    def _load_poets_crew_modules(self):
        import sys

        _, crew_root = self._resolve_crewai_root()
        original_cwd = os.getcwd()
        try:
            os.chdir(crew_root)
            pkg_src = os.path.join(crew_root, "src")
            if pkg_src not in sys.path:
                sys.path.insert(0, pkg_src)

            openrouter_api_key = self._resolve_openrouter_api_key()

            for mod_name in list(sys.modules):
                if mod_name.startswith("poets_crew"):
                    del sys.modules[mod_name]

            from poets_crew.crew import PoetsCrew
            from poets_crew.tools.image_analyzer_tool import ImageAnalyzerTool

            return PoetsCrew, ImageAnalyzerTool, openrouter_api_key
        finally:
            os.chdir(original_cwd)

    @staticmethod
    def _normalize_questions(raw_questions: list[dict[str, Any]]) -> list[dict[str, str]]:
        normalized_questions: list[dict[str, str]] = []
        for index, raw_question in enumerate(raw_questions[:3], start=1):
            question_text = str(raw_question.get("text") or "").strip()
            if not question_text:
                continue

            question: dict[str, str] = {
                "id": f"q{index}",
                "text": question_text,
            }
            kind = str(raw_question.get("kind") or "").strip()
            if kind:
                question["kind"] = kind
            normalized_questions.append(question)

        if not normalized_questions:
            raise RuntimeError("Question generation did not return any valid follow-up questions")

        return normalized_questions

    def _generate_follow_up_questions(
        self,
        image_analysis: str,
        enhance: str | None,
        openrouter_api_key: str,
    ) -> list[dict[str, str]]:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_api_key)
        prompt = (
            "You are preparing a staged poetry workflow. Based on the image analysis and the user's optional note, "
            "write 1 to 3 short follow-up questions that will help poets personalize the final poems. "
            "Return JSON only in the shape {\"questions\": [{\"text\": string, \"kind\": string | null}]}. "
            "The questions must be specific, concrete, and easy to answer in one or two sentences."
        )
        user_context = enhance.strip() if enhance else ""
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "PoetsCrew",
                "X-Title": "PoetsCrew",
            },
            model=self.QUESTION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": (
                        f"Image analysis:\n{image_analysis}\n\n"
                        f"Original user note:\n{user_context or 'None provided.'}"
                    ),
                },
            ],
        )

        response_content = self._extract_text_content(completion.choices[0].message.content)
        if response_content.startswith("```"):
            response_content = response_content.strip("`")
            if response_content.startswith("json"):
                response_content = response_content[4:].strip()

        parsed = json.loads(response_content)
        questions = parsed.get("questions")
        if not isinstance(questions, list):
            raise RuntimeError("Question generation returned an invalid payload")

        return self._normalize_questions(questions)

    @staticmethod
    def _build_generation_context(
        enhance: str | None,
        questions: list[dict[str, str]] | None,
        answers: dict[str, str] | None,
    ) -> str:
        parts: list[str] = []
        if enhance:
            parts.append(f"Original user context:\n{enhance}")

        if questions and answers:
            question_text_by_id = {question["id"]: question["text"] for question in questions if question.get("id")}
            answer_lines = []
            for question_id, answer in answers.items():
                question_text = question_text_by_id.get(question_id, question_id)
                answer_lines.append(f"- {question_text}: {answer}")

            if answer_lines:
                parts.append("Follow-up answers from the user:\n" + "\n".join(answer_lines))

        if not parts:
            return ""

        return "\n\n".join(parts)

    @staticmethod
    def _extract_poems_from_result(result: Any) -> dict[str, str | None]:
        return {
            "poet_modern": result.tasks_output[0].raw if len(result.tasks_output) > 0 else None,
            "poet_classic": result.tasks_output[1].raw if len(result.tasks_output) > 1 else None,
            "poet_mystic": result.tasks_output[2].raw if len(result.tasks_output) > 2 else None,
        }

    @staticmethod
    def _run_async(awaitable: Any) -> Any:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(awaitable)
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    async def _with_thread_db(self, callback):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from ..core.config import settings

        engine = create_async_engine(
            settings.POSTGRES_ASYNC_DATABASE_URL,
            echo=False,
            future=True,
        )
        async_session = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        try:
            async with async_session() as db:
                return await callback(db)
        finally:
            await engine.dispose()

    def _run_stage_1_sync(
        self,
        poem_source_id: int,
        media_path: str,
        user_id: int,
        enhance: str | None,
    ) -> dict[str, Any]:
        local_image_path = ""
        should_cleanup_local_image = False

        try:
            _, ImageAnalyzerTool, openrouter_api_key = self._load_poets_crew_modules()
            local_image_path, should_cleanup_local_image = storage_service.prepare_local_media_file(media_path)

            tool = ImageAnalyzerTool(
                api_key=openrouter_api_key,
                model="qwen/qwen3-vl-235b-a22b-instruct",
            )
            image_analysis = tool._run(image_path=local_image_path).strip()
            logger.info("Stage 1 image analysis completed for source_id=%s", poem_source_id)

            normalized_analysis = image_analysis.lower()
            if normalized_analysis == self.INDISTINCT_CONTENT_MESSAGE:
                raise RuntimeError(self.INDISTINCT_CONTENT_MESSAGE)
            if normalized_analysis.startswith("error analyzing image:"):
                raise RuntimeError(image_analysis)

            questions = self._generate_follow_up_questions(image_analysis, enhance, openrouter_api_key)
            self._persist_output_artifacts(poem_source_id=poem_source_id, image_analysis=image_analysis)

            async def persist_stage_1(db: AsyncSession) -> None:
                await self._update_poem_source(
                    db,
                    poem_source_id,
                    status="stage_1",
                    image_analysis=image_analysis,
                    follow_up_questions=questions,
                    error_message=None,
                )

            self._run_async(self._with_thread_db(persist_stage_1))
            return {
                "image_analysis": image_analysis,
                "questions": questions,
            }
        except Exception as exc:
            logger.error("Stage 1 failed for source_id=%s: %s", poem_source_id, exc)
            logger.error("Full traceback:\n%s", traceback.format_exc())
            error_message = self._normalize_error_message(exc)

            async def persist_error(db: AsyncSession) -> None:
                await self._update_poem_source(
                    db,
                    poem_source_id,
                    status="error",
                    error_message=error_message,
                )

            self._run_async(self._with_thread_db(persist_error))
            return {"image_analysis": "", "questions": []}
        finally:
            if should_cleanup_local_image and local_image_path and os.path.exists(local_image_path):
                try:
                    os.remove(local_image_path)
                except OSError as cleanup_error:
                    logger.warning(
                        "Failed to clean up temporary local image %s: %s",
                        local_image_path,
                        cleanup_error,
                    )

    def _run_stage_2_sync(self, poem_source_id: int) -> dict[str, Any]:
        local_image_path = ""
        should_cleanup_local_image = False

        try:
            PoetsCrew, _, _ = self._load_poets_crew_modules()

            async def load_source(db: AsyncSession) -> dict[str, Any] | None:
                from ..crud.crud_poem_sources import crud_poem_sources
                from ..schemas.poem_source import PoemSourceWorkflowRead

                return await crud_poem_sources.get(
                    db=db,
                    id=poem_source_id,
                    is_deleted=False,
                    schema_to_select=PoemSourceWorkflowRead,
                )

            poem_source = self._run_async(self._with_thread_db(load_source))
            if poem_source is None:
                raise RuntimeError("Poem source not found")

            media_path = poem_source.get("media_path")
            user_id = poem_source.get("user_id")
            image_analysis = poem_source.get("image_analysis")
            questions = poem_source.get("follow_up_questions") or []
            answers = poem_source.get("follow_up_answers") or {}

            if not media_path or not user_id or not image_analysis:
                raise RuntimeError("Poem source is missing staged workflow data")
            if not answers:
                raise RuntimeError("Poem source is missing follow-up answers")

            local_image_path, should_cleanup_local_image = storage_service.prepare_local_media_file(media_path)
            prompt_context = self._build_generation_context(
                poem_source.get("enhance"),
                questions,
                answers,
            )
            inputs = {
                "image_path": local_image_path,
                "image_analysis": image_analysis,
                "enhance": f"\n\n{prompt_context}" if prompt_context else "",
            }
            result = self._kickoff_with_fallback(PoetsCrew, inputs)
            poems = self._extract_poems_from_result(result)
            self._persist_output_artifacts(
                poem_source_id=poem_source_id,
                image_analysis=image_analysis,
                poems=poems,
            )

            async def persist_stage_2(db: AsyncSession) -> None:
                try:
                    await self._save_poems(
                        db=db,
                        user_id=user_id,
                        poem_source_id=poem_source_id,
                        poems={key: value or "" for key, value in poems.items()},
                        commit=False,
                    )
                    await self._update_poem_source(
                        db,
                        poem_source_id,
                        status="complete",
                        error_message=None,
                        commit=False,
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

            self._run_async(self._with_thread_db(persist_stage_2))
            return {
                "image_analysis": image_analysis,
                "poems": poems,
            }
        except Exception as exc:
            logger.error("Stage 2 failed for source_id=%s: %s", poem_source_id, exc)
            logger.error("Full traceback:\n%s", traceback.format_exc())
            error_message = self._normalize_error_message(exc)

            async def persist_error(db: AsyncSession) -> None:
                await self._update_poem_source(
                    db,
                    poem_source_id,
                    status="error",
                    error_message=error_message,
                )

            self._run_async(self._with_thread_db(persist_error))
            return {"image_analysis": "", "poems": {}}
        finally:
            if should_cleanup_local_image and local_image_path and os.path.exists(local_image_path):
                try:
                    os.remove(local_image_path)
                except OSError as cleanup_error:
                    logger.warning(
                        "Failed to clean up temporary local image %s: %s",
                        local_image_path,
                        cleanup_error,
                    )

    def start_stage_1_analysis(
        self,
        poem_source_id: int,
        media_path: str,
        user_id: int,
        enhance: str | None,
    ) -> None:
        self.executor.submit(
            self._run_stage_1_sync,
            poem_source_id,
            media_path,
            user_id,
            enhance,
        )

    def start_stage_2_generation(self, poem_source_id: int) -> None:
        self.executor.submit(self._run_stage_2_sync, poem_source_id)

crewai_service = CrewAIService()
