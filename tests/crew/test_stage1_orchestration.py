"""Regression tests for stage-1 crew orchestration (agents a–c)."""

import time
from contextlib import ExitStack
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.api.v1.poem_source import check_poem_source_ready
from src.app.schemas.poem_source import PoemSourceStatus
from src.app.services.crewai.service import CrewAIService
from tests.fixtures.poets import poet_card_fixtures

ACTIVE_POETS = [{"id": 11, "name": "Walt Whitman"}]
WITH_THREAD_DB_PATH = "src.app.services.crewai.service.persistence.with_thread_db"
RUN_ASYNC_PATH = "src.app.services.crewai.service.persistence.run_async"
PICKER_PATH = "src.app.services.crewai.service.generate_poet_candidate_ids"


class _FakeImageAnalyzerTool:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def _run(self, image_path: str) -> str:
        return "A quiet lake under morning light."


class TestStage1Orchestration:
    def test_persists_questions_and_poet_candidates(self) -> None:
        service = CrewAIService()
        poet_cards = [poet_card_fixtures()[0].model_dump()]

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.load_poets_crew_modules",
                    return_value=(_FakeImageAnalyzerTool, "key"),
                )
            )
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.storage_service.prepare_local_media_file",
                    return_value=("/tmp/image.png", False),
                )
            )
            stack.enter_context(patch.object(service, "_load_active_poets", return_value=ACTIVE_POETS))
            stack.enter_context(patch.object(service, "_load_poet_cards", return_value=poet_cards))
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.generate_follow_up_questions",
                    return_value=[{"id": "q1", "text": "What feeling?"}],
                )
            )
            stack.enter_context(patch(PICKER_PATH, return_value=[11]))
            stack.enter_context(patch("src.app.services.crewai.service.persist_output_artifacts"))
            stack.enter_context(patch(WITH_THREAD_DB_PATH, new=Mock(return_value=object())))
            stack.enter_context(patch(RUN_ASYNC_PATH))

            result = service._run_stage_1_sync(7, "media/a.png", 1, None)

        assert result == {
            "image_analysis": "A quiet lake under morning light.",
            "questions": [{"id": "q1", "text": "What feeling?"}],
            "poet_candidates": poet_cards,
        }

    def test_questions_and_poet_picker_run_in_parallel(self) -> None:
        service = CrewAIService()

        def _slow_questions(*_args) -> list[dict[str, str]]:
            time.sleep(0.1)
            return [{"id": "q1", "text": "What feeling?"}]

        def _slow_picker(*_args) -> list[int]:
            time.sleep(0.1)
            return [11]

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.load_poets_crew_modules",
                    return_value=(_FakeImageAnalyzerTool, "key"),
                )
            )
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.storage_service.prepare_local_media_file",
                    return_value=("/tmp/image.png", False),
                )
            )
            stack.enter_context(patch.object(service, "_load_active_poets", return_value=ACTIVE_POETS))
            stack.enter_context(patch.object(service, "_load_poet_cards", return_value=[]))
            stack.enter_context(
                patch("src.app.services.crewai.service.generate_follow_up_questions", side_effect=_slow_questions)
            )
            stack.enter_context(patch(PICKER_PATH, side_effect=_slow_picker))
            stack.enter_context(patch("src.app.services.crewai.service.persist_output_artifacts"))
            stack.enter_context(patch(WITH_THREAD_DB_PATH, new=Mock(return_value=object())))
            stack.enter_context(patch(RUN_ASYNC_PATH))

            started_at = time.perf_counter()
            service._run_stage_1_sync(7, "media/a.png", 1, None)
            elapsed = time.perf_counter() - started_at

        assert elapsed < 0.18

    def test_poet_picker_failure_keeps_stage_1_successful_with_empty_candidates(self) -> None:
        service = CrewAIService()

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.load_poets_crew_modules",
                    return_value=(_FakeImageAnalyzerTool, "key"),
                )
            )
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.storage_service.prepare_local_media_file",
                    return_value=("/tmp/image.png", False),
                )
            )
            stack.enter_context(patch.object(service, "_load_active_poets", return_value=ACTIVE_POETS))
            mock_load_cards = stack.enter_context(patch.object(service, "_load_poet_cards", return_value=[]))
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.generate_follow_up_questions",
                    return_value=[{"id": "q1", "text": "What feeling?"}],
                )
            )
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.generate_poet_candidate_ids",
                    side_effect=RuntimeError("picker down"),
                )
            )
            stack.enter_context(patch("src.app.services.crewai.service.persist_output_artifacts"))
            stack.enter_context(patch(WITH_THREAD_DB_PATH, new=Mock(return_value=object())))
            stack.enter_context(patch(RUN_ASYNC_PATH))

            result = service._run_stage_1_sync(7, "media/a.png", 1, None)

        assert result["questions"] == [{"id": "q1", "text": "What feeling?"}]
        assert result["poet_candidates"] == []
        mock_load_cards.assert_called_once_with([])


@pytest.mark.asyncio
async def test_ready_returns_200_with_empty_candidates_when_picker_failed(
    mock_db, current_user_dict
) -> None:
    """URL-resume after a picker failure still returns stage_1 with empty cards."""
    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        with patch("src.app.services.crewai.prompts.generate_poet_candidate_ids") as mock_picker:
            mock_get.return_value = {
                "id": 7,
                "status": PoemSourceStatus.STAGE_1.value,
                "follow_up_questions": [{"id": "q1", "text": "What feeling?"}],
                "poet_candidates": [],
                "error_message": None,
            }

            result = await check_poem_source_ready(Mock(), 7, mock_db, current_user_dict)

    mock_picker.assert_not_called()
    assert result["ready"] is True
    assert result["status"] == PoemSourceStatus.STAGE_1.value
    assert result["questions"] == [{"id": "q1", "text": "What feeling?"}]
    assert result["poet_candidates"] == []
